import json
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from galaxy.processing_config import (
    MappingConfig,
    PlaneNormalizationConfig,
    RGBMixConfig,
    StretchConfig,
    ToneConfig,
)
from galaxy.mapping import (
    CompositionInputs,
    RGBContribution,
    compose_channels,
    compose_channels_with_diagnostics,
    mix_display_planes,
    normalize_plane_for_display,
)
from galaxy.reprojection import ReprojectedPlane
from galaxy.tone import (
    apply_shared_intensity,
    apply_tone,
    generalized_hyperbolic_stretch,
    propose_auto_stretch,
)


def _inputs(
    planes: dict[str, np.ndarray],
    metadata: dict[str, dict[str, object]],
    footprints: dict[str, np.ndarray] | None = None,
    *,
    grid_ids: dict[str, str] | None = None,
) -> CompositionInputs:
    return CompositionInputs({
        name: ReprojectedPlane(
            name,
            values,
            (footprints or {}).get(name, np.ones_like(values, dtype=np.float32)),
            metadata.get(name, {}),
            wcs=_celestial_wcs((grid_ids or {}).get(name, "grid-a")),
        )
        for name, values in planes.items()
    })


def _celestial_wcs(grid_key: str = "grid-a") -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0 + sum(ord(character) for character in grid_key) / 1000.0, 20.0]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    return wcs


def test_mapping_and_tone_generate_rgb_cube() -> None:
    planes = {
        "blue_plane": np.full((8, 8), 1.0, dtype=np.float32),
        "green_plane": np.full((8, 8), 2.0, dtype=np.float32),
        "red_plane": np.full((8, 8), 3.0, dtype=np.float32),
    }
    metadata = {
        "blue_plane": {"filter": "F090W"},
        "green_plane": {"filter": "F200W"},
        "red_plane": {"filter": "F444W"},
    }
    mapping = MappingConfig.model_validate(
        {
            "planes": [
                {"plane": "red_plane", "rgb": {"red": 1.0, "green": 0.0, "blue": 0.0}},
                {"plane": "green_plane", "rgb": {"red": 0.0, "green": 1.0, "blue": 0.0}},
                {"plane": "blue_plane", "rgb": {"red": 0.0, "green": 0.0, "blue": 1.0}},
            ]
        }
    )
    tone = ToneConfig.model_validate(
        {
            "stretch": {
                "red": {"kind": "asinh", "parameter": 4.0},
                "green": {"kind": "asinh", "parameter": 4.0},
                "blue": {"kind": "asinh", "parameter": 4.0},
            },
            "percentiles": {"black": 0.0, "white": 100.0},
        }
    )
    composed = compose_channels(_inputs(planes, metadata), mapping)
    rgb = apply_tone(composed, tone)
    assert rgb.shape == (8, 8, 3)
    assert rgb.dtype == np.float32 or rgb.dtype == np.float64


def test_filter_based_plane_mapping_matches_metadata_filters() -> None:
    planes = {
        "jwst_f444w": np.full((4, 4), 5.0, dtype=np.float32),
        "jwst_f300m": np.full((4, 4), 3.0, dtype=np.float32),
        "jwst_f140m": np.full((4, 4), 1.0, dtype=np.float32),
    }
    metadata = {
        "jwst_f444w": {"filter": "F444W"},
        "jwst_f300m": {"filter": "F300M"},
        "jwst_f140m": {"filter": "F140M"},
    }
    mapping = MappingConfig.model_validate(
        {
            "planes": [
                {"filter": "F444W", "label": "dust", "rgb": {"red": 1.0, "green": 0.2, "blue": 0.0}},
                {"filter": "F300M", "label": "gas", "rgb": {"red": 0.0, "green": 1.0, "blue": 0.2}},
                {"filter": "F140M", "label": "stars", "rgb": {"red": 0.1, "green": 0.2, "blue": 1.0}},
            ]
        }
    )

    composed = compose_channels(_inputs(planes, metadata), mapping)

    assert np.allclose(composed["red"], 5.1)
    assert np.allclose(composed["green"], 4.2)
    assert np.allclose(composed["blue"], 1.6)


def test_default_mapping_spreads_planes_across_continuum() -> None:
    planes = {
        "f090w": np.ones((2, 2), dtype=np.float32),
        "f200w": np.ones((2, 2), dtype=np.float32),
        "f444w": np.ones((2, 2), dtype=np.float32),
    }
    metadata = {
        "f090w": {"filter": "F090W"},
        "f200w": {"filter": "F200W"},
        "f444w": {"filter": "F444W"},
    }
    mapping = MappingConfig.model_validate({})

    composed = compose_channels(_inputs(planes, metadata), mapping)

    assert composed["blue"][0, 0] > 0.0
    assert composed["green"][0, 0] > 0.0
    assert composed["red"][0, 0] > 0.0
    assert composed["green"][0, 0] >= composed["blue"][0, 0]


def test_percentile_normalization_gain_matches_different_native_scales() -> None:
    pattern = np.arange(100, dtype=np.float32).reshape(10, 10)
    planes = {"small": pattern, "large": pattern * 1000.0}
    metadata = {
        "small": {"filter": "F502N", "native_unit": "ELECTRONS/S"},
        "large": {"filter": "F200W", "native_unit": "MJy/sr"},
    }
    mapping = MappingConfig.model_validate({
        "defaults": {"normalization": {
            "mode": "percentile", "black_percentile": 0.0,
            "white_percentile": 100.0, "stretch": "linear", "gain": 1.0,
        }},
        "planes": [
            {"plane": "small", "rgb": {"red": 1.0}},
            {"plane": "large", "rgb": {"green": 1.0}},
        ],
    })

    result = compose_channels_with_diagnostics(_inputs(planes, metadata), mapping)

    assert np.allclose(result.channels["red"], result.channels["green"])
    assert result.warnings == []
    assert result.plane_diagnostics["small"]["black_point"] == 0.0
    assert result.plane_diagnostics["large"]["white_point"] == 99000.0


def test_native_mixed_units_warn_and_report_contribution() -> None:
    planes = {
        "hst": np.ones((4, 4), dtype=np.float32),
        "jwst": np.full((4, 4), 100.0, dtype=np.float32),
    }
    metadata = {
        "hst": {"filter": "F502N", "native_unit": "ELECTRONS/S"},
        "jwst": {"filter": "F200W", "native_unit": "MJy/sr"},
    }
    mapping = MappingConfig.model_validate({
        "planes": [
            {"plane": "hst", "rgb": {"red": 1.0}},
            {"plane": "jwst", "rgb": {"red": 1.0}},
        ]
    })

    result = compose_channels_with_diagnostics(_inputs(planes, metadata), mapping)

    assert "Mixed native FITS units" in result.warnings[0]
    assert result.plane_diagnostics["hst"]["rgb_contribution_percent"]["red"] == pytest.approx(100 / 101)


def test_percentile_normalization_excludes_pixels_outside_footprint() -> None:
    image = np.array([[1.0, 2.0], [10000.0, 10000.0]], dtype=np.float32)
    alternate = np.array([[1.0, 2.0], [-1e12, 1e12]], dtype=np.float32)
    footprint = np.array([[1.0, 1.0], [0.0, 0.0]], dtype=np.float32)
    mapping = MappingConfig.model_validate({
        "defaults": {"normalization": {
            "mode": "percentile", "black_percentile": 0.0,
            "white_percentile": 100.0, "stretch": "linear",
        }},
        "planes": [{"plane": "plane", "rgb": {"red": 1.0}}],
    })

    result = compose_channels_with_diagnostics(
        _inputs({"plane": image}, {"plane": {"filter": "F200W"}}, {"plane": footprint}),
        mapping,
    )
    alternate_result = compose_channels_with_diagnostics(
        _inputs({"plane": alternate}, {"plane": {"filter": "F200W"}}, {"plane": footprint}),
        mapping,
    )

    assert result.plane_diagnostics["plane"]["white_point"] == 2.0
    assert np.array_equal(result.channels["red"], alternate_result.channels["red"])
    assert np.array_equal(result.channel_coverage["red"], alternate_result.channel_coverage["red"])
    assert np.all(result.channels["red"][1] == 0.0)
    assert np.all(result.channel_coverage["red"][0])
    assert not np.any(result.channel_coverage["red"][1])


def test_output_tone_percentiles_exclude_uncovered_pixels() -> None:
    channels = {
        channel: np.array([[0.0, 0.0, 10.0, 20.0, 30.0]], dtype=np.float32)
        for channel in ("red", "green", "blue")
    }
    masks = {
        channel: np.array([[False, False, True, True, True]])
        for channel in channels
    }
    tone = ToneConfig.model_validate({
        "stretch": {
            channel: {"kind": "gamma", "parameter": 1.0}
            for channel in channels
        },
        "percentiles": {"black": 0.0, "white": 100.0},
    })

    rgb = apply_tone(channels, tone, bit_depth=8, valid_masks=masks)

    assert np.all(rgb[0, :3] == 0.0)
    assert np.all(rgb[0, 3] == 127.5)
    assert np.all(rgb[0, 4] == 255.0)


def test_derived_ratio_masks_missing_and_near_zero_denominators() -> None:
    numerator = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    denominator = np.array([[1.0, 0.0], [1e-8, -2.0]], dtype=np.float32)
    metadata = {
        "numerator": {"native_unit": "MJy/sr"},
        "denominator": {"native_unit": "MJy/sr"},
    }
    mapping = MappingConfig.model_validate({
        "derived_planes": [{
            "name": "ratio",
            "operation": "ratio",
            "numerator": [{"plane": "numerator"}],
            "denominator": [{"plane": "denominator"}],
            "epsilon": 1e-6,
        }],
        "planes": [{"plane": "ratio", "rgb": {"red": 1.0}}],
    })

    result = compose_channels_with_diagnostics(
        _inputs({"numerator": numerator, "denominator": denominator}, metadata), mapping
    )

    assert np.array_equal(result.channel_coverage["red"], [[True, False], [False, True]])
    assert result.channels["red"][0, 1] == 0.0
    assert result.channels["red"][1, 0] == 0.0
    assert result.channels["red"][1, 1] == pytest.approx(-2.0)


def test_derived_arithmetic_rejects_mismatched_grid_identity() -> None:
    planes = {"left": np.ones((2, 2), dtype=np.float32), "right": np.ones((2, 2), dtype=np.float32)}
    mapping = MappingConfig.model_validate({
        "derived_planes": [{
            "name": "sum",
            "operation": "linear_combination",
            "terms": [{"plane": "left"}, {"plane": "right"}],
        }],
        "planes": [{"plane": "sum", "rgb": {"red": 1.0}}],
    })

    with pytest.raises(ValueError, match="same grid"):
        compose_channels_with_diagnostics(
            _inputs(planes, {"left": {}, "right": {}}, grid_ids={"left": "a", "right": "b"}),
            mapping,
        )


def test_derived_arithmetic_does_not_mutate_input_packages() -> None:
    left = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    right = np.array([[4.0, 3.0], [2.0, 1.0]], dtype=np.float32)
    left_coverage = np.array([[1.0, 0.5], [1.0, 1.0]], dtype=np.float32)
    right_coverage = np.array([[1.0, 1.0], [0.25, 1.0]], dtype=np.float32)
    inputs = _inputs(
        {"left": left, "right": right},
        {"left": {}, "right": {}},
        {"left": left_coverage, "right": right_coverage},
    )
    snapshots = {
        name: (package.data.copy(), package.footprint.copy())
        for name, package in inputs.planes.items()
    }
    mapping = MappingConfig.model_validate({
        "derived_planes": [{
            "name": "sum",
            "operation": "linear_combination",
            "terms": [{"plane": "left"}, {"plane": "right", "weight": -0.5}],
        }],
        "planes": [{"plane": "sum", "rgb": {"red": 1.0}}],
    })

    compose_channels_with_diagnostics(inputs, mapping)

    for name, package in inputs.planes.items():
        expected_data, expected_coverage = snapshots[name]
        assert np.array_equal(package.data, expected_data)
        assert np.array_equal(package.footprint, expected_coverage)


def test_composition_rejects_display_domain_as_linear_input() -> None:
    package = ReprojectedPlane(
        "display", np.ones((2, 2), dtype=np.float32), np.ones((2, 2), dtype=np.float32), {},
        wcs=_celestial_wcs(),
        domain="display_plane",
    )

    with pytest.raises(ValueError, match="unsupported composition domain"):
        CompositionInputs({"display": package})


def test_normalization_and_rgb_mixing_use_explicit_typed_stage_results() -> None:
    source = _inputs(
        {"source": np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)},
        {"source": {"native_unit": "MJy/sr"}},
    ).planes["source"]
    source_values = source.data.copy()
    source_valid = source.valid.copy()
    source_coverage = source.coverage.copy()
    policy = MappingConfig.model_validate({
        "defaults": {"normalization": {
            "mode": "percentile", "black_percentile": 0.0,
            "white_percentile": 100.0, "stretch": "linear", "gain": 1.0,
        }}
    }).defaults.normalization

    normalized = normalize_plane_for_display(source, policy)
    mixed = mix_display_planes(
        source,
        [RGBContribution(normalized.plane, RGBMixConfig(red=1.0, green=0.5, blue=0.0))],
        )

    assert normalized.plane.domain == "display_plane"
    assert normalized.plane.unit == "unitless"
    assert normalized.plane.grid_id == source.grid_id
    assert normalized.plane.parent_ids == ("source",)
    assert np.array_equal(mixed.channel_coverage["red"], source.valid)
    assert np.allclose(mixed.channels["green"], mixed.channels["red"] * 0.5)
    assert np.array_equal(source.data, source_values)
    assert np.array_equal(source.valid, source_valid)
    assert np.array_equal(source.coverage, source_coverage)
    assert not np.shares_memory(normalized.plane.data, source.data)


def test_fixed_bound_normalization_uses_persisted_values_without_reestimation() -> None:
    plane = ReprojectedPlane(
        "fixed", np.array([[0.0, 10.0], [20.0, 1000.0]], dtype=np.float32),
        np.ones((2, 2), dtype=np.float32), {}, wcs=_celestial_wcs("grid-a"),
    )
    policy = PlaneNormalizationConfig(
        mode="fixed_bounds", black_value=10.0, white_value=20.0,
        stretch="linear", gain=1.0,
    )

    result = normalize_plane_for_display(plane, policy)

    assert np.array_equal(result.plane.data, [[0.0, 0.0], [1.0, 1.0]])
    assert result.diagnostics["black_point"] == 10.0
    assert result.diagnostics["white_point"] == 20.0


def test_fixed_bound_normalization_rejects_missing_or_reversed_values() -> None:
    with pytest.raises(ValueError, match="requires black_value and white_value"):
        PlaneNormalizationConfig(mode="fixed_bounds")
    with pytest.raises(ValueError, match="black_value must be lower"):
        PlaneNormalizationConfig(mode="fixed_bounds", black_value=2.0, white_value=1.0)


def test_locked_reference_rejects_stale_branch_identity() -> None:
    plane = ReprojectedPlane(
        "fixed", np.arange(4, dtype=np.float32).reshape(2, 2),
        np.ones((2, 2), dtype=np.float32), {"native_unit": "MJy/sr"},
        wcs=_celestial_wcs("grid-a"), branch="deconvolved", source_ids=("source-a",),
    )
    policy = PlaneNormalizationConfig.model_validate({
        "mode": "fixed_bounds", "black_value": 0.0, "white_value": 3.0,
        "reference": {
            "reference_id": "ref", "kind": "region", "region_ids": ["sky"],
            "branch": "original", "grid_id": plane.grid_id, "source_ids": ["source-a"],
            "unit": "MJy/sr", "coverage_policy": "available_contributors",
            "black_percentile": 0.0, "white_percentile": 100.0,
            "black_value": 0.0, "white_value": 3.0, "sample_count": 4,
            "low_clipping_fraction": 0.0, "high_clipping_fraction": 0.0,
            "locked": True,
        },
    })

    with pytest.raises(ValueError, match="stale normalization reference identity"):
        normalize_plane_for_display(plane, policy)

def test_rgb_mixing_rejects_non_display_plane_inputs() -> None:
    source = _inputs({"source": np.ones((2, 2), dtype=np.float32)}, {"source": {}}).planes["source"]

    with pytest.raises(ValueError, match="unsupported RGB-mixing domain"):
        mix_display_planes(source, [RGBContribution(source, RGBMixConfig(red=1.0))])


def test_frozen_phase0_legacy_recipe_matches_known_answer() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "processing_upgrade" / "numeric_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    definitions = fixture["planes"]
    selected = ("low_scale", "high_scale_masked_outlier", "constant")
    values = {
        name: np.asarray(definitions[name]["values"], dtype=np.float32)
        for name in selected
    }
    coverage = {
        name: np.asarray(definitions[name]["coverage"], dtype=np.float32)
        for name in selected
    }
    metadata = {
        name: {"native_unit": definitions[name]["unit"]}
        for name in selected
    }
    inputs = _inputs(values, metadata, coverage)
    mapping = MappingConfig.model_validate({
        "defaults": {"normalization": {
            "mode": "percentile", "black_percentile": 0.0,
            "white_percentile": 100.0, "stretch": "linear", "gain": 1.0,
        }},
        "planes": [
            {"plane": "low_scale", "rgb": {"red": 1.0}},
            {"plane": "high_scale_masked_outlier", "rgb": {"green": 1.0}},
            {"plane": "constant", "rgb": {"blue": 1.0}},
        ],
    })
    tone = ToneConfig.model_validate({
        "stretch": {
            channel: {"kind": "gamma", "parameter": 1.0}
            for channel in ("red", "green", "blue")
        },
        "percentiles": {"black": 0.0, "white": 100.0},
        "gain": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "bias": {"red": 0.0, "green": 0.0, "blue": 0.0},
        "saturation": 1.0,
    })

    composed = compose_channels_with_diagnostics(inputs, mapping)
    actual = apply_tone(composed.channels, tone, valid_masks=composed.channel_coverage)

    expected = np.zeros((*values["low_scale"].shape, 3), dtype=np.float32)
    expected[..., 0] = values["low_scale"] / 15.0
    high_valid = np.asarray(definitions["high_scale_masked_outlier"]["valid"], dtype=bool)
    expected[..., 1][high_valid] = values["high_scale_masked_outlier"][high_valid] / 14000.0
    expected *= 65535.0
    tolerance = fixture["float_tolerance"]

    assert np.allclose(actual, expected, rtol=tolerance["rtol"], atol=tolerance["atol"])


def test_shared_intensity_preserves_supported_ratios_before_and_after_rescale() -> None:
    rgb = np.array([[[0.2, 0.4, 0.8], [0.3, 0.6, 0.0]]], dtype=np.float64)
    masks = np.array([[[True, True, True], [True, True, False]]])
    stretch = StretchConfig(kind="asinh", parameter=20.0)

    result = apply_shared_intensity(rgb, stretch, masks, "rescale")

    assert result[0, 0, 0] / result[0, 0, 1] == pytest.approx(0.5, rel=1e-12)
    assert result[0, 0, 1] / result[0, 0, 2] == pytest.approx(0.5, rel=1e-12)
    assert result[0, 1, 0] / result[0, 1, 1] == pytest.approx(0.5, rel=1e-12)
    assert result[0, 1, 2] == 0.0


def test_shared_intensity_zero_and_signed_policy_are_explicit() -> None:
    stretch = StretchConfig(kind="asinh", parameter=4.0)
    zero = np.zeros((1, 1, 3), dtype=np.float64)
    assert np.array_equal(apply_shared_intensity(zero, stretch), zero)
    with pytest.raises(ValueError, match="negative RGB"):
        apply_shared_intensity(np.array([[[-0.1, 0.2, 0.3]]]), stretch)


def test_shared_intensity_clip_and_rescale_have_distinct_gamut_behavior() -> None:
    rgb = np.array([[[1.0, 0.5, 0.25]]], dtype=np.float64)
    stretch = StretchConfig(kind="asinh", parameter=20.0)
    clipped = apply_shared_intensity(rgb, stretch, gamut_policy="clip")
    rescaled = apply_shared_intensity(rgb, stretch, gamut_policy="rescale")
    assert clipped[0, 0, 0] == 1.0
    assert clipped[0, 0, 1] / clipped[0, 0, 0] != pytest.approx(0.5)
    assert rescaled[0, 0, 1] / rescaled[0, 0, 0] == pytest.approx(0.5)


@pytest.mark.parametrize("local_intensity", [-2.0, -1.0, 0.0, 1.0, 4.0])
def test_ghs_is_finite_monotone_endpoint_normalized_and_continuous(
    local_intensity: float,
) -> None:
    x = np.linspace(0.0, 1.0, 10001)
    result = generalized_hyperbolic_stretch(
        x, stretch_factor=2.0, local_intensity=local_intensity,
        symmetry_point=0.35, shadow_protection=0.1, highlight_protection=0.8,
    )
    assert result.dtype == np.float64
    assert np.all(np.isfinite(result))
    assert result[0] == pytest.approx(0.0, abs=1e-12)
    assert result[-1] == pytest.approx(1.0, abs=1e-12)
    assert np.min(np.diff(result)) >= -1e-12
    for boundary in (0.1, 0.35, 0.8):
        left = generalized_hyperbolic_stretch(
            np.array([boundary - 1e-9]), stretch_factor=2.0,
            local_intensity=local_intensity, symmetry_point=0.35,
            shadow_protection=0.1, highlight_protection=0.8,
        )[0]
        right = generalized_hyperbolic_stretch(
            np.array([boundary + 1e-9]), stretch_factor=2.0,
            local_intensity=local_intensity, symmetry_point=0.35,
            shadow_protection=0.1, highlight_protection=0.8,
        )[0]
        assert right - left < 1e-7


def test_ghs_published_exponential_subtype_reference_and_identity() -> None:
    x = np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float64)
    stretch_factor = np.log(5.0)
    actual = generalized_hyperbolic_stretch(
        x, stretch_factor=stretch_factor, local_intensity=0.0,
        symmetry_point=0.0, shadow_protection=0.0, highlight_protection=1.0,
    )
    d_value = 4.0
    expected = (1.0 - np.exp(-d_value * x)) / (1.0 - np.exp(-d_value))
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)
    identity = generalized_hyperbolic_stretch(
        x, stretch_factor=0.0, local_intensity=15.0,
        symmetry_point=0.5, shadow_protection=0.5, highlight_protection=0.5,
    )
    assert np.array_equal(identity, x)


def test_ghs_processing_model_rejects_missing_and_misordered_parameters() -> None:
    with pytest.raises(ValueError, match="all five"):
        StretchConfig(kind="ghs", stretch_factor=1.0)
    with pytest.raises(ValueError, match="shadow_protection"):
        StretchConfig(
            kind="ghs", stretch_factor=1.0, local_intensity=2.0,
            symmetry_point=0.4, shadow_protection=0.5, highlight_protection=0.8,
        )


def test_auto_stretch_proposal_is_deterministic_and_places_reference_median() -> None:
    yy, xx = np.indices((32, 32), dtype=np.float64)
    base = 0.02 + (xx + yy) * 1e-5
    rgb = np.stack((base, base * 1.2, base * 0.8), axis=-1)
    mask = np.ones((32, 32), dtype=bool)
    kwargs = dict(
        reference_id="background-key", branch="original", grid_id="grid-a",
        source_ids=["source-a"], minimum_samples=256,
    )
    first = propose_auto_stretch(rgb, mask, **kwargs)
    second = propose_auto_stretch(rgb, mask, **kwargs)
    assert first == second
    mapped = np.arcsinh(first.resolved_parameter * first.source_median) / np.arcsinh(
        first.resolved_parameter
    )
    assert mapped == pytest.approx(0.1, abs=1e-12)
    assert first.locked is True


def test_auto_stretch_rejects_insufficient_constant_and_already_bright_samples() -> None:
    mask = np.ones((32, 32), dtype=bool)
    kwargs = dict(
        reference_id="background-key", branch="original", grid_id="grid-a",
        source_ids=["source-a"], minimum_samples=256,
    )
    with pytest.raises(ValueError, match="below minimum"):
        propose_auto_stretch(np.ones((8, 8, 3)) * 0.02, np.ones((8, 8), bool), **kwargs)
    with pytest.raises(ValueError, match="constant"):
        propose_auto_stretch(np.ones((32, 32, 3)) * 0.02, mask, **kwargs)
    gradient = np.linspace(0.15, 0.2, 1024).reshape(32, 32)
    with pytest.raises(ValueError, match="above target"):
        propose_auto_stretch(np.repeat(gradient[..., None], 3, axis=-1), mask, **kwargs)
    background = np.linspace(0.015, 0.025, 716)
    objects = np.full(308, 0.09)
    object_dominated = np.concatenate((background, objects)).reshape(32, 32)
    with pytest.raises(ValueError, match="object-dominated"):
        propose_auto_stretch(
            np.repeat(object_dominated[..., None], 3, axis=-1), mask, **kwargs
        )

import numpy as np
from astropy.wcs import WCS
from tifffile import imread

from galaxy.pipeline import _compose_and_export_branch
from galaxy.planes import build_plane_records
from galaxy.processing_config import CoverageConfig, GalaxyConfig
from galaxy.rendering import render_aligned_planes
from galaxy.reprojection import ReprojectedPlane


def _config() -> GalaxyConfig:
    return GalaxyConfig.model_validate({
        "target": {"name": "test", "region": {"kind": "circle", "radius_arcmin": 1.0}},
        "canvas": {
            "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
            "pixel_scale_arcsec": 1.0, "width": 3, "height": 2,
        },
        "mapping": {"planes": [{
            "plane": "plane", "rgb": {"red": 1.0, "green": 0.5, "blue": 0.25},
            "normalization": {
                "mode": "percentile", "black_percentile": 0.0,
                "white_percentile": 100.0, "stretch": "linear", "gain": 1.0,
            },
        }]},
        "tone": {
            "stretch": {channel: {"kind": "gamma", "parameter": 1.0}
                        for channel in ("red", "green", "blue")},
            "percentiles": {"black": 0.0, "white": 100.0},
        },
    })


def _plane() -> ReprojectedPlane:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]
    coverage = np.array([[0.0, 1.0, 1.0], [0.0, 0.5, 1.0]], dtype=np.float32)
    return ReprojectedPlane(
        "plane",
        np.array([[1e9, 1.0, 2.0], [-1e9, 3.0, 4.0]], dtype=np.float32),
        coverage,
        {"native_unit": "MJy/sr"},
        wcs=wcs,
    )


def test_scene_export_and_direct_preview_share_numeric_core_with_partial_support(tmp_path) -> None:
    config = _config()
    planes = [_plane()]
    direct = render_aligned_planes(planes, config.mapping, config.tone, bit_depth=16)
    records = build_plane_records(planes, set())

    _, tiff_path, _, _, coverage_stage, _, _ = _compose_and_export_branch(
        planes,
        records,
        config,
        tmp_path / "composite.png",
        tmp_path / "composite.tiff",
    )

    assert np.array_equal(imread(tiff_path), direct.rgb.astype(np.uint16))
    assert coverage_stage["algorithm_ids"] == ["COVERAGE-001"]
    assert not np.any(direct.composition.channel_coverage["red"][:, 0])
    assert np.all(direct.rgb[:, 0] == 0.0)


def test_common_required_support_retains_holes_and_all_disconnected_components() -> None:
    config = _config()
    wcs = _plane().wcs
    first = ReprojectedPlane(
        "plane", np.arange(20, dtype=np.float32).reshape(4, 5),
        np.ones((4, 5), dtype=np.float32), {"native_unit": "MJy/sr"}, wcs=wcs,
    )
    second_valid = np.array([
        [True, True, False, False, False],
        [True, False, False, False, False],
        [False, False, False, False, True],
        [False, False, False, True, True],
    ])
    second = ReprojectedPlane(
        "second", np.arange(20, dtype=np.float32).reshape(4, 5),
        second_valid.astype(np.float32), {"native_unit": "MJy/sr"}, wcs=first.wcs,
    )
    mapping = config.mapping.model_copy(update={"planes": [
        config.mapping.planes[0],
        config.mapping.planes[0].model_copy(update={"plane": "second"}),
    ]})

    result = render_aligned_planes(
        [first, second], mapping, config.tone,
        coverage=CoverageConfig(policy="common_required_bands"),
    )

    assert np.array_equal(result.coverage.support, second_valid & first.valid)
    assert result.coverage.diagnostics["component_count"] == 2
    assert np.all(result.rgb[~result.coverage.support] == 0)


def test_bounding_crop_padding_updates_wcs_without_changing_common_pixels() -> None:
    config = _config()
    plane = _plane()
    uncropped = render_aligned_planes(
        [plane], config.mapping, config.tone,
        coverage=CoverageConfig(policy="common_required_bands"),
    )
    cropped = render_aligned_planes(
        [plane], config.mapping, config.tone,
        coverage=CoverageConfig(
            policy="common_required_bands", crop="bounding_box", padding_pixels=0,
        ),
    )

    assert cropped.rgb.shape == (2, 2, 3)
    assert np.array_equal(cropped.rgb, uncropped.rgb[:, 1:])
    assert cropped.coverage.diagnostics["crop_bounds_xyxy"] == [1, 0, 3, 2]
    expected_world = plane.wcs.pixel_to_world_values(1, 0)
    actual_world = cropped.coverage.output_wcs.pixel_to_world_values(0, 0)
    assert np.allclose(actual_world, expected_world)


def test_empty_common_required_support_fails_visibly() -> None:
    config = _config()
    first = _plane()
    second = ReprojectedPlane(
        "second", np.ones((2, 3), dtype=np.float32),
        np.array([[1, 0, 0], [1, 0, 0]], dtype=np.float32),
        {"native_unit": "MJy/sr"}, wcs=first.wcs,
    )
    mapping = config.mapping.model_copy(update={"planes": [
        config.mapping.planes[0],
        config.mapping.planes[0].model_copy(update={"plane": "second"}),
    ]})

    with np.testing.assert_raises_regex(ValueError, "common required-band support is empty"):
        render_aligned_planes(
            [first, second], mapping, config.tone,
            coverage=CoverageConfig(policy="common_required_bands"),
        )


def test_union_output_can_use_common_tone_reference_without_brightening_partial_support() -> None:
    config = _config()
    first = _plane()
    second = ReprojectedPlane(
        "second", np.array([[9.0, 1.0, 2.0], [9.0, 3.0, 4.0]], dtype=np.float32),
        np.array([[1, 1, 0], [1, 1, 1]], dtype=np.float32),
        {"native_unit": "MJy/sr"}, wcs=first.wcs,
    )
    mapping = config.mapping.model_copy(update={"planes": [
        config.mapping.planes[0],
        config.mapping.planes[0].model_copy(update={"plane": "second"}),
    ]})
    accepted = render_aligned_planes(
        [first, second], mapping, config.tone,
        coverage=CoverageConfig(tone_reference="common_required_bands"),
    )
    common_only = render_aligned_planes(
        [first, second], mapping, config.tone,
        coverage=CoverageConfig(
            policy="common_required_bands", tone_reference="common_required_bands",
        ),
    )

    common = accepted.composition.required_support
    union = np.logical_or.reduce(list(accepted.composition.channel_coverage.values()))
    assert np.array_equal(accepted.coverage.support, union)
    assert np.array_equal(accepted.rgb[common], common_only.rgb[common])
    assert np.any(accepted.rgb[union & ~common] != 0)
    assert accepted.coverage.diagnostics["excluded_pixel_count"] == 0
    assert accepted.coverage.diagnostics["tone_reference_pixel_count"] == int(
        np.count_nonzero(common)
    )

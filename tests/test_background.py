from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from galaxy.background import (
    BackgroundSamplingError,
    apply_background,
    estimate_background,
    write_background_diagnostics,
    write_background_overlay,
)
from galaxy.processing_config import (
    BackgroundConfig,
    BackgroundEstimatorConfig,
    MappingConfig,
    PlaneMappingConfig,
    PlaneNormalizationConfig,
    RGBMixConfig,
    SkyRectangleConfig,
    StretchConfig,
    ToneConfig,
    ToneGainBias,
    TonePercentiles,
    ToneStretchSet,
)
from galaxy.rendering import render_aligned_planes
from galaxy.reprojection import ReprojectedPlane


def _wcs(shape: tuple[int, int]) -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [(shape[1] + 1) / 2, (shape[0] + 1) / 2]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]
    return wcs


def _plane(data: np.ndarray, *, plane_id: str = "plane-a", valid=None) -> ReprojectedPlane:
    coverage = np.ones(data.shape, dtype=np.float32)
    coverage[:2, :] = 0
    if valid is None:
        valid = coverage > 0
    return ReprojectedPlane(
        plane_id,
        np.asarray(data, dtype=np.float32),
        coverage,
        {"filter": "F200W", "native_unit": "MJy/sr", "artifact_branch": "original"},
        wcs=_wcs(data.shape),
        valid=np.asarray(valid, dtype=bool),
        branch="original",
        source_ids=(f"source-{plane_id}",),
        parent_ids=(f"native-{plane_id}",),
    )


def _region(region_id: str, wcs: WCS, x: float, y: float, width: float, height: float) -> SkyRectangleConfig:
    ra, dec = wcs.pixel_to_world_values(x, y)
    return SkyRectangleConfig(
        region_id=region_id,
        center_ra_deg=float(ra),
        center_dec_deg=float(dec),
        width_arcsec=width,
        height_arcsec=height,
    )


def _config(plane: ReprojectedPlane, *, exclusion: bool = True) -> BackgroundConfig:
    exclusions = (
        [_region("protected-source", plane.wcs, 80, 80, 14, 14)] if exclusion else []
    )
    return BackgroundConfig(
        mode="pedestal",
        black_reference_policy="corrected_zero",
        inclusion_regions=[_region("sky", plane.wcs, 63.5, 63.5, 120, 120)],
        exclusion_regions=exclusions,
        estimator=BackgroundEstimatorConfig(
            clip_sigma=3.0,
            max_iterations=5,
            minimum_samples=256,
            minimum_valid_fraction=0.5,
        ),
    )


def _applied(config: BackgroundConfig, proposal) -> BackgroundConfig:
    return BackgroundConfig.model_validate({
        **config.model_dump(mode="json"),
        "resolved_branches": {
            "original": {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in proposal.resolved_planes.items()
            }
        },
    })


def _mapping_and_tone() -> tuple[MappingConfig, ToneConfig]:
    mapping = MappingConfig(
        planes=[PlaneMappingConfig(
            plane="plane-a",
            rgb=RGBMixConfig(red=1, green=1, blue=1),
            normalization=PlaneNormalizationConfig(
                mode="percentile", black_percentile=10, white_percentile=99,
                stretch="linear", stretch_parameter=1, gain=1,
            ),
        )]
    )
    stretches = ToneStretchSet(**{
        channel: StretchConfig(kind="gamma", parameter=1)
        for channel in ("red", "green", "blue")
    })
    tone = ToneConfig(
        stretch=stretches,
        percentiles=TonePercentiles(black=10, white=99),
        gain=ToneGainBias(),
        bias=ToneGainBias(red=0, green=0, blue=0),
        saturation=1,
    )
    return mapping, tone


def test_seeded_pedestal_estimate_and_protected_signal_acceptance(tmp_path: Path) -> None:
    rng = np.random.default_rng(20260928)
    noise_sigma = 2.0
    noise = rng.normal(0.0, noise_sigma, (128, 128)).astype(np.float32)
    source_mask = np.zeros((128, 128), dtype=bool)
    source_mask[75:86, 75:86] = True
    signal = np.zeros((128, 128), dtype=np.float32)
    signal[source_mask] = 10.0
    data = 50.0 + noise + signal
    data[20, 20] = 50000.0
    plane = _plane(data)
    config = _config(plane)

    proposal = estimate_background([plane], config)
    record = proposal.resolved_planes[plane.plane_id]
    applied = apply_background([plane], _applied(config, proposal))
    corrected = applied.planes[0]

    assert abs(record.pedestal - 50.0) <= 0.1 * noise_sigma
    expected_signal = float(np.sum(signal[source_mask] + noise[source_mask]))
    actual_signal = float(np.sum(corrected.data[source_mask]))
    assert abs(actual_signal - expected_signal) / abs(expected_signal) < 0.01
    assert np.array_equal(corrected.coverage, plane.coverage)
    assert corrected.grid_id == plane.grid_id
    assert corrected.source_ids == plane.source_ids
    assert float(corrected.data[10, 10]) < 0
    assert applied.stage_record is not None
    assert applied.stage_record["stage_id"] == "background_pedestal"

    diagnostic = write_background_diagnostics(proposal, tmp_path / "background.json")
    overlay = write_background_overlay(proposal, tmp_path / "background.png")
    assert diagnostic.is_file()
    assert overlay.is_file()


def test_common_mask_ignores_invalid_extreme_and_reports_insufficient_samples() -> None:
    rng = np.random.default_rng(20260928)
    data = 12.0 + rng.normal(0, 1, (64, 64)).astype(np.float32)
    valid = np.ones((64, 64), dtype=bool)
    valid[:2, :] = False
    valid[20, 20] = False
    first = _plane(data, valid=valid)
    changed = data.copy()
    changed[20, 20] = 1e20
    second = _plane(changed, valid=valid)
    config = BackgroundConfig(
        mode="pedestal",
        black_reference_policy="corrected_zero",
        inclusion_regions=[_region("sky", first.wcs, 31.5, 31.5, 60, 60)],
        estimator=BackgroundEstimatorConfig(minimum_samples=100, minimum_valid_fraction=0.5),
    )

    one = estimate_background([first], config).resolved_planes["plane-a"].pedestal
    two = estimate_background([second], config).resolved_planes["plane-a"].pedestal
    assert one == two

    strict = config.model_copy(deep=True)
    strict.estimator.minimum_samples = 5000
    with pytest.raises(BackgroundSamplingError, match="below minimum"):
        estimate_background([first], strict)


def test_off_mode_is_numerically_identical() -> None:
    plane = _plane(np.arange(64, dtype=np.float32).reshape(8, 8))
    result = apply_background([plane], BackgroundConfig())
    assert result.planes[0] is plane
    assert result.stage_record is None


def test_corrected_zero_does_not_cancel_pedestal_and_preserves_unsupported_pixels() -> None:
    rng = np.random.default_rng(20260928)
    data = 10.0 + rng.normal(0, 0.2, (64, 64)).astype(np.float32)
    data[28:36, 28:36] += 1.0
    plane = _plane(data)
    config = BackgroundConfig(
        mode="pedestal",
        black_reference_policy="corrected_zero",
        inclusion_regions=[_region("sky", plane.wcs, 15, 15, 20, 20)],
        estimator=BackgroundEstimatorConfig(minimum_samples=100, minimum_valid_fraction=0.5),
    )
    proposal = estimate_background([plane], config)
    corrected = _applied(config, proposal)
    legacy = corrected.model_copy(deep=True)
    legacy.black_reference_policy = "legacy_percentile"
    mapping, tone = _mapping_and_tone()

    legacy_rgb = render_aligned_planes(
        [plane], mapping, tone, background=legacy, bit_depth=16
    ).rgb
    corrected_rgb = render_aligned_planes(
        [plane], mapping, tone, background=corrected, bit_depth=16
    ).rgb

    sky = np.s_[10:20, 10:20, :]
    source = np.s_[28:36, 28:36, :]
    assert float(np.median(corrected_rgb[sky])) < float(np.median(legacy_rgb[sky]))
    assert float(np.median(corrected_rgb[source])) > float(np.median(corrected_rgb[sky]))
    assert np.all(corrected_rgb[:2, :, :] == 0)

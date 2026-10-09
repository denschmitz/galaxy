import numpy as np
import pytest
from astropy.wcs import WCS

from galaxy.background import BackgroundSamplingError
from galaxy.normalization_reference import estimate_normalization_references
from galaxy.processing_config import BackgroundConfig, CoverageConfig
from galaxy.reprojection import ReprojectedPlane


def _wcs() -> WCS:
    result = WCS(naxis=2)
    result.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    result.wcs.crval = [10.0, 20.0]
    result.wcs.crpix = [2.0, 2.0]
    result.wcs.cdelt = [-1 / 3600, 1 / 3600]
    return result


def _plane(name: str, offset: float = 0.0) -> ReprojectedPlane:
    return ReprojectedPlane(
        name, np.arange(16, dtype=np.float32).reshape(4, 4) + offset,
        np.ones((4, 4), dtype=np.float32), {"native_unit": "MJy/sr"},
        wcs=_wcs(), source_ids=(f"source:{name}",),
    )


def _background() -> BackgroundConfig:
    return BackgroundConfig.model_validate({
        "inclusion_regions": [{
            "region_id": "sky", "center_ra_deg": 10.0, "center_dec_deg": 20.0,
            "width_arcsec": 20.0, "height_arcsec": 20.0,
        }],
    })


def test_region_reference_records_locked_identity_and_resolved_bounds() -> None:
    proposal = estimate_normalization_references(
        [_plane("a"), _plane("b", 100.0)], _background(), CoverageConfig(),
        black_percentile=25.0, white_percentile=75.0,
    )

    assert set(proposal.references) == {"a", "b"}
    assert proposal.references["a"].locked is True
    assert proposal.references["a"].reference_id == proposal.references["b"].reference_id
    assert proposal.references["a"].black_value == pytest.approx(3.75)
    assert proposal.references["a"].white_value == pytest.approx(11.25)
    assert proposal.references["b"].black_value == pytest.approx(103.75)
    assert proposal.references["a"].sample_count == 16


def test_region_reference_rejects_constant_samples() -> None:
    plane = _plane("constant")
    plane.data[:] = 4.0
    with pytest.raises(BackgroundSamplingError, match="constant or nonfinite"):
        estimate_normalization_references(
            [plane], _background(), CoverageConfig(),
            black_percentile=10.0, white_percentile=90.0,
        )


def test_region_reference_rejects_missing_region() -> None:
    with pytest.raises(BackgroundSamplingError, match="persisted inclusion region"):
        estimate_normalization_references(
            [_plane("a")], BackgroundConfig(), CoverageConfig(),
            black_percentile=10.0, white_percentile=90.0,
        )

from __future__ import annotations

import numpy as np
import pytest
from astropy.wcs import WCS

from galaxy.fitsio import FITSPlane
from galaxy.viewport_framing import MAX_PREVIEW_DIMENSION, fit_planes, render_fit_preview


def _plane(identity: str, ra: float, dec: float, *, rotation: float = 0.0) -> FITSPlane:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [30.0, 20.0]
    scale = 0.5 / 3600.0
    angle = np.deg2rad(rotation)
    wcs.wcs.cd = scale * np.array([
        [-np.cos(angle), np.sin(angle)],
        [np.sin(angle), np.cos(angle)],
    ])
    return FITSPlane(identity, np.ones((40, 60), dtype=np.float32), wcs, {})


def test_fit_contains_overlapping_rotated_support_with_tight_orientation() -> None:
    result = fit_planes([
        _plane("a", 359.999, -2.0, rotation=31.0),
        _plane("b", 0.001, -2.0, rotation=31.0),
    ], ["mast:a", "mast:b"])

    assert result.warnings == ()
    assert result.canvas["frame_origin"] == "selected_footprints"
    assert 0.0 <= float(result.canvas["rotation_deg"]) < 180.0
    assert int(result.canvas["width"]) <= MAX_PREVIEW_DIMENSION
    assert int(result.canvas["height"]) <= MAX_PREVIEW_DIMENSION
    assert result.diagnostics.component_count == 1
    assert result.diagnostics.frame_width_deg < 0.02

    preview = render_fit_preview(result, maximum_dimension=256)
    assert preview.ndim == 3 and preview.shape[2] == 3
    assert max(preview.shape[:2]) <= 256
    # The white canvas border is not the only visible geometry: selected support
    # outlines must remain visible inside the proposed frame.
    assert np.count_nonzero(preview[3:-3, 3:-3]) > 40


def test_fit_warns_for_disconnected_widely_separated_scans_and_caps_preview() -> None:
    result = fit_planes([
        _plane("a", 10.0, 20.0),
        _plane("b", 16.0, 20.0),
    ], ["mast:a", "mast:b"])

    assert result.warnings
    assert result.diagnostics.component_count == 2
    assert result.diagnostics.angular_span_deg > 5.0
    assert max(result.diagnostics.width, result.diagnostics.height) == MAX_PREVIEW_DIMENSION
    warning = " ".join(result.warnings)
    assert "mast:a" in warning and "mast:b" in warning
    assert "estimated memory" in warning


def test_fit_rejects_product_with_no_valid_pixels() -> None:
    plane = _plane("empty", 10.0, 20.0)
    plane.mask = np.ones_like(plane.data, dtype=bool)

    with pytest.raises(ValueError, match="mast:empty.*no valid pixels"):
        fit_planes([plane], ["mast:empty"])

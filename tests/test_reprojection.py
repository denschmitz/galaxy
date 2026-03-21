from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS
import numpy as np
import pytest

from galaxy import reprojection
from galaxy.config import CanvasConfig
from galaxy.fitsio import FITSPlane
from galaxy.reprojection import build_output_wcs, derive_reference_output_wcs, reproject_plane


def test_reprojection_preserves_center_peak() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [16.0, 16.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]

    image = np.zeros((32, 32), dtype=np.float32)
    image[16, 16] = 1.0
    plane = FITSPlane("synthetic", image, wcs, {"filter": "F200W"})

    canvas = CanvasConfig.model_validate(
        {
            "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
            "pixel_scale_arcsec": 1.0,
            "width": 32,
            "height": 32,
        }
    )
    output_wcs, shape_out = build_output_wcs(canvas, SkyCoord(10 * u.deg, 20 * u.deg))
    reprojected = reproject_plane(plane, output_wcs, shape_out, flux_conserving=False)
    max_y, max_x = np.unravel_index(np.argmax(reprojected.data), reprojected.data.shape)
    assert abs(max_x - 15) <= 1
    assert abs(max_y - 15) <= 1


def test_flux_conserving_reprojection_returns_finite_output() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [16.0, 16.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]

    image = np.zeros((32, 32), dtype=np.float32)
    image[16, 16] = 5.0
    plane = FITSPlane("synthetic", image, wcs, {"filter": "F200W"})

    canvas = CanvasConfig.model_validate(
        {
            "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
            "pixel_scale_arcsec": 1.0,
            "width": 32,
            "height": 32,
            "flux_conserving": True,
        }
    )
    output_wcs, shape_out = build_output_wcs(canvas, SkyCoord(10 * u.deg, 20 * u.deg))
    reprojected = reproject_plane(plane, output_wcs, shape_out, flux_conserving=True)
    assert np.isfinite(reprojected.data).all()
    assert np.isfinite(reprojected.footprint).all()


def test_reference_workspace_uses_first_plane_orientation_and_expands_union() -> None:
    ref_wcs = WCS(naxis=2)
    ref_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    ref_wcs.wcs.crval = [10.0, 20.0]
    ref_wcs.wcs.crpix = [16.0, 16.0]
    ref_wcs.wcs.cd = np.array([[-0.0002, 0.0001], [0.0001, 0.0002]])

    second_wcs = ref_wcs.deepcopy()
    second_wcs.wcs.crval = [10.004, 20.003]

    ref_plane = FITSPlane("ref", np.zeros((32, 32), dtype=np.float32), ref_wcs, {"filter": "F502N"})
    second_plane = FITSPlane("other", np.zeros((32, 32), dtype=np.float32), second_wcs, {"filter": "F657N"})

    output_wcs, shape_out, diagnostics = derive_reference_output_wcs([ref_plane, second_plane], expand_fraction=0.10)

    assert diagnostics["reference_plane_id"] == "ref"
    assert shape_out[0] > 32
    assert shape_out[1] > 32
    assert np.allclose(output_wcs.wcs.cd, ref_wcs.wcs.cd)


def test_reference_workspace_rejects_pathologically_large_union(monkeypatch) -> None:
    ref_wcs = WCS(naxis=2)
    ref_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    ref_wcs.wcs.crval = [10.0, 20.0]
    ref_wcs.wcs.crpix = [16.0, 16.0]
    ref_wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    ref_plane = FITSPlane("ref", np.zeros((32, 32), dtype=np.float32), ref_wcs, {"filter": "F502N"})

    monkeypatch.setattr(reprojection, "_projected_union_bounds", lambda planes, reference_wcs: (0.0, 0.0, 200000.0, 200000.0))

    with pytest.raises(ValueError, match="derived workspace is unreasonably large"):
        derive_reference_output_wcs([ref_plane], expand_fraction=0.10)


def test_reference_workspace_allows_large_total_pixels_within_dimension_limit(monkeypatch) -> None:
    ref_wcs = WCS(naxis=2)
    ref_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    ref_wcs.wcs.crval = [10.0, 20.0]
    ref_wcs.wcs.crpix = [16.0, 16.0]
    ref_wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    ref_plane = FITSPlane("ref", np.zeros((32, 32), dtype=np.float32), ref_wcs, {"filter": "F502N"})

    monkeypatch.setattr(reprojection, "_projected_union_bounds", lambda planes, reference_wcs: (0.0, 0.0, 15856.0, 11899.0))

    _, shape_out, diagnostics = derive_reference_output_wcs([ref_plane], expand_fraction=0.0)

    assert shape_out == (11900, 15857)
    assert diagnostics["width"] == 15857
    assert diagnostics["height"] == 11900

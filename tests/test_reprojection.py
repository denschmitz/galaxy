from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS
import numpy as np

from galaxy.config import CanvasConfig
from galaxy.fitsio import FITSPlane
from galaxy.reprojection import build_output_wcs, reproject_plane


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

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from galaxy.fitsio import load_fits_plane


def _write_sample_fits(path: Path) -> None:
    primary = fits.PrimaryHDU()
    primary.header["FILTER"] = "F200W"
    primary.header["INSTRUME"] = "NIRCAM"
    primary.header["DETECTOR"] = "NRCA1"
    primary.header["TELESCOP"] = "JWST"
    primary.header["OBS_ID"] = "OBS-1"
    primary.header["EXPTIME"] = 123.4

    science = fits.ImageHDU(data=np.arange(16, dtype=np.float32).reshape(4, 4), name="SCI")
    science.header["CTYPE1"] = "RA---TAN"
    science.header["CTYPE2"] = "DEC--TAN"
    science.header["CRPIX1"] = 2.0
    science.header["CRPIX2"] = 2.0
    science.header["CRVAL1"] = 10.0
    science.header["CRVAL2"] = 20.0
    science.header["CDELT1"] = -0.0002777778
    science.header["CDELT2"] = 0.0002777778

    dq = fits.ImageHDU(
        data=np.array([[0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 2, 0], [0, 0, 0, 0]], dtype=np.int16),
        name="DQ",
    )
    fits.HDUList([primary, science, dq]).writeto(path)


def test_load_fits_plane_reads_science_data_and_primary_header_fallback(tmp_path) -> None:
    source = tmp_path / "sample.fits"
    _write_sample_fits(source)

    plane = load_fits_plane(source)

    assert plane.plane_id == "sample"
    assert plane.data.shape == (4, 4)
    assert plane.metadata["filter"] == "F200W"
    assert plane.metadata["instrument"] == "NIRCAM"
    assert plane.metadata["detector"] == "NRCA1"
    assert plane.metadata["mission"] == "JWST"
    assert plane.metadata["observation_id"] == "OBS-1"
    assert plane.metadata["exposure_time"] == 123.4
    assert plane.mask is not None
    assert plane.mask.dtype == bool
    assert plane.mask[0, 1]
    assert plane.mask[2, 2]


def test_load_fits_plane_rejects_missing_wcs(tmp_path) -> None:
    source = tmp_path / "no_wcs.fits"
    fits.PrimaryHDU(data=np.ones((4, 4), dtype=np.float32)).writeto(source)

    with pytest.raises(ValueError, match="missing WCS"):
        load_fits_plane(source)

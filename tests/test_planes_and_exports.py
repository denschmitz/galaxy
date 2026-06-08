import numpy as np
from PIL import Image
from astropy.io import fits
from astropy.wcs import WCS
from tifffile import imread

from galaxy.export import export_footprint_overlay, export_png, export_tiff
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_records
from galaxy.reprojection import ReprojectedPlane


def test_export_multiplane_fits_round_trip_preserves_plane_metadata(tmp_path) -> None:
    output_wcs = WCS(naxis=2)
    output_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    output_wcs.wcs.crval = [10.0, 20.0]
    output_wcs.wcs.crpix = [2.0, 2.0]
    output_wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    planes = [
        ReprojectedPlane(
            "plane_a",
            np.full((4, 4), 1.0, dtype=np.float32),
            np.ones((4, 4), dtype=np.float32),
            {
                "filter": "F200W",
                "mission": "JWST",
                "instrument": "NIRCAM",
                "detector": "NRCA1",
                "observation_id": "OBS-1",
                "exposure_time": 123.4,
            },
        )
    ]

    destination = export_multiplane_fits(planes, tmp_path / "planes.fits", output_wcs=output_wcs)
    loaded = load_multiplane_records(destination)
    records = build_plane_records(loaded, disabled_plane_ids={"plane_a"})
    header = fits.getheader(destination, ext=1)

    assert loaded[0].plane_id == "plane_a"
    assert loaded[0].metadata["filter"] == "F200W"
    assert loaded[0].metadata["header_subset"]["CTYPE1"] == "RA---TAN"
    assert header["CRVAL1"] == 10.0
    assert records[0].enabled is False
    assert records[0].mission == "JWST"


def test_export_png_and_tiff_write_expected_pixel_formats(tmp_path) -> None:
    rgb = np.dstack(
        [
            np.full((4, 4), 65535, dtype=np.float32),
            np.full((4, 4), 32768, dtype=np.float32),
            np.zeros((4, 4), dtype=np.float32),
        ]
    )

    png_path = export_png(rgb, tmp_path / "image.png")
    tiff_path = export_tiff(rgb, tmp_path / "image.tiff")

    png = np.asarray(Image.open(png_path))
    tiff = imread(tiff_path)

    assert png.dtype == np.uint8
    assert png.shape == (4, 4, 3)
    assert tiff.dtype == np.uint16
    assert tiff.shape == (4, 4, 3)


def test_export_footprint_overlay_renders_white_boundaries_on_black_background(tmp_path) -> None:
    footprint = np.zeros((6, 6), dtype=np.float32)
    footprint[1:5, 1:5] = 1.0

    overlay_path = export_footprint_overlay([footprint], tmp_path / "footprints.png")
    overlay = np.asarray(Image.open(overlay_path))

    assert overlay.shape == (6, 6)
    assert overlay[0, 0] == 0
    assert overlay[1, 1] == 255
    assert overlay[2, 2] == 0

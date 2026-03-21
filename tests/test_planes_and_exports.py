import numpy as np
from PIL import Image
from tifffile import imread

from galaxy.export import export_png, export_tiff
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_records
from galaxy.reprojection import ReprojectedPlane


def test_export_multiplane_fits_round_trip_preserves_plane_metadata(tmp_path) -> None:
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

    destination = export_multiplane_fits(planes, tmp_path / "planes.fits")
    loaded = load_multiplane_records(destination)
    records = build_plane_records(loaded, disabled_plane_ids={"plane_a"})

    assert loaded[0].plane_id == "plane_a"
    assert loaded[0].metadata["filter"] == "F200W"
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

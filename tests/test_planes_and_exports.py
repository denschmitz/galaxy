import numpy as np
import pytest
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
                "native_unit": "MJy/sr",
                "mask_sources": ["WHT"],
                "valid_coverage_fraction": 0.75,
            },
            wcs=output_wcs.deepcopy(),
        )
    ]

    destination = export_multiplane_fits(planes, tmp_path / "planes.fits", output_wcs=output_wcs)
    loaded = load_multiplane_records(destination)
    records = build_plane_records(loaded, disabled_plane_ids={"plane_a"})
    header = fits.getheader(destination, ext=1)

    assert loaded[0].plane_id == "plane_a"
    assert loaded[0].metadata["filter"] == "F200W"
    assert loaded[0].metadata["native_unit"] == "MJy/sr"
    assert loaded[0].metadata["mask_sources"] == ["WHT"]
    assert np.array_equal(loaded[0].footprint, planes[0].footprint)
    assert loaded[0].metadata["header_subset"]["CTYPE1"] == "RA---TAN"
    assert loaded[0].wcs is not None
    assert np.allclose(
        loaded[0].wcs.pixel_to_world_values(1.0, 1.0),
        output_wcs.pixel_to_world_values(1.0, 1.0),
        rtol=0.0,
        atol=1e-10,
    )
    assert loaded[0].grid_id != "legacy:(4, 4)"
    assert header["CRVAL1"] == 10.0
    assert records[0].enabled is False
    assert records[0].mission == "JWST"
    assert records[0].valid_coverage_fraction == 0.75


def test_legacy_stack_requires_explicit_fallback_wcs_for_typed_inspection(tmp_path) -> None:
    path = tmp_path / "legacy.fits"
    primary = fits.PrimaryHDU()
    science = fits.ImageHDU(data=np.ones((4, 4), dtype=np.float32), name="LEGACY")
    science.header["PLANEID"] = "legacy"
    coverage = fits.ImageHDU(data=np.ones((4, 4), dtype=np.float32), name="LEGACY_COVERAGE")
    coverage.header["GALTYPE"] = "FOOTPRINT"
    coverage.header["PARENT"] = "legacy"
    fits.HDUList([primary, science, coverage]).writeto(path)
    fallback = WCS(naxis=2)
    fallback.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    fallback.wcs.crval = [10.0, 20.0]
    fallback.wcs.crpix = [2.0, 2.0]
    fallback.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]

    with pytest.raises(ValueError, match="celestial WCS"):
        load_multiplane_records(path)
    loaded = load_multiplane_records(path, legacy_fallback_wcs=fallback)

    assert len(loaded) == 1
    assert loaded[0].wcs is not None
    assert loaded[0].grid_id
    assert np.allclose(
        loaded[0].wcs.pixel_to_world_values(1.0, 1.0),
        fallback.pixel_to_world_values(1.0, 1.0),
        rtol=0.0,
        atol=1e-10,
    )


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


def test_reprojected_plane_rejects_invalid_coverage_contract() -> None:
    with np.testing.assert_raises_regex(ValueError, "coverage must be finite within"):
        ReprojectedPlane(
            "bad",
            np.ones((2, 2), dtype=np.float32),
            np.array([[1.0, 1.1], [0.0, np.nan]], dtype=np.float32),
            {},
            wcs=WCS(fits.Header({
                "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
                "CRPIX1": 1.0, "CRPIX2": 1.0,
                "CRVAL1": 10.0, "CRVAL2": 20.0,
                "CDELT1": -0.0002777778, "CDELT2": 0.0002777778,
            })),
        )


def test_reprojected_plane_rejects_missing_celestial_geometry() -> None:
    with np.testing.assert_raises_regex(ValueError, "two-dimensional celestial WCS"):
        ReprojectedPlane(
            "bad-geometry",
            np.ones((2, 2), dtype=np.float32),
            np.ones((2, 2), dtype=np.float32),
            {},
        )


def test_reprojected_plane_rejects_grid_identity_that_disagrees_with_wcs() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]

    with np.testing.assert_raises_regex(ValueError, "grid identity disagrees"):
        ReprojectedPlane(
            "bad-grid",
            np.ones((2, 2), dtype=np.float32),
            np.ones((2, 2), dtype=np.float32),
            {},
            wcs=wcs,
            grid_id="caller-supplied-mismatch",
        )


def test_reprojected_plane_rejects_nonfinite_usable_values() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]

    with np.testing.assert_raises_regex(ValueError, "nonfinite usable values"):
        ReprojectedPlane(
            "bad-finite",
            np.array([[1.0, np.nan], [2.0, 3.0]], dtype=np.float32),
            np.ones((2, 2), dtype=np.float32),
            {},
            wcs=wcs,
            valid=np.ones((2, 2), dtype=bool),
        )

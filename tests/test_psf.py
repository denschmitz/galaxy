import shutil
from pathlib import Path
import uuid

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from scipy.signal import convolve2d

from galaxy.processing_config import PSFConfig, PSFPlaneConfig
from galaxy.fitsio import FITSPlane
from galaxy.psf import (
    _celestial_pixel_scales_arcsec,
    _gaussian_kernel_from_fwhm,
    _richardson_lucy,
    apply_presentation_psf,
    build_deconvolved_plane_artifacts,
)


def _celestial_wcs() -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [3.0, 3.0]
    wcs.wcs.cdelt = [-0.1 / 3600.0, 0.1 / 3600.0]
    return wcs


def test_psf_enabled_requires_resolvable_kernel() -> None:
    with pytest.raises(ValueError):
        apply_presentation_psf({"plane": np.ones((5, 5), dtype=np.float32)}, PSFConfig(enabled=True))


def test_psf_enabled_applies_deconvolution_with_common_kernel() -> None:
    truth = np.zeros((21, 21), dtype=np.float32)
    truth[10, 10] = 1.0
    kernel = np.array([[0.0, 0.125, 0.0], [0.125, 0.5, 0.125], [0.0, 0.125, 0.0]], dtype=np.float32)
    image = convolve2d(truth, kernel, mode="same", boundary="symm").astype(np.float32)

    processed = apply_presentation_psf(
        {"plane": image},
        PSFConfig(enabled=True, common_psf_fwhm_arcsec=2.0),
        pixel_scales_arcsec={"plane": (1.0, 1.0)},
    )

    assert processed["plane"].shape == image.shape
    assert processed["plane"].dtype == np.float32
    assert processed["plane"][10, 10] > image[10, 10]


def test_psf_enabled_uses_per_plane_kernel_file() -> None:
    temp_root = Path.cwd() / ".tmp_test_psf"
    temp_root.mkdir(exist_ok=True)
    test_dir = temp_root / str(uuid.uuid4())
    test_dir.mkdir()
    try:
        kernel = np.array([[0.0, 0.125, 0.0], [0.125, 0.5, 0.125], [0.0, 0.125, 0.0]], dtype=np.float32)
        kernel_path = test_dir / "kernel.fits"
        fits.PrimaryHDU(data=kernel).writeto(kernel_path)

        truth = np.zeros((15, 15), dtype=np.float32)
        truth[7, 7] = 1.0
        image = convolve2d(truth, kernel, mode="same", boundary="symm").astype(np.float32)

        processed = apply_presentation_psf(
            {"plane": image},
            PSFConfig(
                enabled=True,
                per_plane={
                    "plane": PSFPlaneConfig(enabled=True, kernel_path=str(kernel_path), max_iterations=6, regularization=0.1)
                },
            ),
        )

        assert processed["plane"][7, 7] > image[7, 7]
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_native_frame_branch_retains_explicitly_unprocessed_planes(tmp_path: Path) -> None:
    kernel_path = tmp_path / "kernel.fits"
    fits.PrimaryHDU(data=np.ones((3, 3), dtype=np.float32)).writeto(kernel_path)
    planes = [
        FITSPlane("processed", np.eye(5, dtype=np.float32), _celestial_wcs(), {}),
        FITSPlane("original-copy", np.ones((5, 5), dtype=np.float32), _celestial_wcs(), {}),
    ]
    result = build_deconvolved_plane_artifacts(
        planes,
        PSFConfig(enabled=True, per_plane={
            "processed": PSFPlaneConfig(enabled=True, kernel_path=str(kernel_path)),
            "original-copy": PSFPlaneConfig(enabled=False),
        }),
        tmp_path,
    )
    copied = next(plane for plane in result if plane.plane_id == "original-copy")
    assert np.array_equal(copied.data, planes[1].data)
    assert copied.metadata["psf_processed"] is False


def test_masked_values_do_not_change_valid_richardson_lucy_output() -> None:
    kernel = np.array([[0.0, 0.125, 0.0], [0.125, 0.5, 0.125], [0.0, 0.125, 0.0]])
    valid = np.ones((9, 9), dtype=bool)
    valid[4, 4] = False
    first = np.ones((9, 9), dtype=np.float32)
    second = first.copy()
    first[4, 4] = 1e6
    second[4, 4] = 1e12

    first_result = _richardson_lucy(first, kernel, 4, 0.0, valid)
    second_result = _richardson_lucy(second, kernel, 4, 0.0, valid)

    assert np.allclose(first_result[valid], second_result[valid], rtol=1e-6, atol=1e-6)
    assert first_result[4, 4] == 0.0


def test_richardson_lucy_rejects_valid_negative_samples() -> None:
    image = np.ones((5, 5), dtype=np.float32)
    image[2, 2] = -1.0

    with pytest.raises(ValueError, match="nonnegative valid samples"):
        _richardson_lucy(image, np.ones((3, 3)), 2, 0.0)


def test_gaussian_kernel_converts_angular_width_to_pixel_sampling() -> None:
    fine = _gaussian_kernel_from_fwhm(0.2, (0.1, 0.1))
    coarse = _gaussian_kernel_from_fwhm(0.2, (0.2, 0.2))
    anisotropic = _gaussian_kernel_from_fwhm(0.2, (0.1, 0.2))

    assert fine.shape[0] > coarse.shape[0]
    assert anisotropic.shape[1] > anisotropic.shape[0]
    assert float(fine.sum()) == pytest.approx(1.0, abs=1e-7)
    assert float(coarse.sum()) == pytest.approx(1.0, abs=1e-7)


def test_celestial_wcs_supplies_native_pixel_scales() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [5.0, 5.0]
    wcs.wcs.cdelt = [-0.1 / 3600.0, 0.2 / 3600.0]

    scales = _celestial_pixel_scales_arcsec(wcs)

    assert scales == pytest.approx((0.1, 0.2), rel=1e-9)


def test_common_angular_kernel_requires_sampling_geometry() -> None:
    with pytest.raises(ValueError, match="celestial WCS or explicit pixel scales"):
        apply_presentation_psf(
            {"plane": np.ones((5, 5), dtype=np.float32)},
            PSFConfig(enabled=True, common_psf_fwhm_arcsec=0.2),
        )

import shutil
from pathlib import Path
import uuid

import numpy as np
import pytest
from astropy.io import fits
from scipy.signal import convolve2d

from galaxy.config import PSFConfig, PSFPlaneConfig
from galaxy.psf import apply_presentation_psf


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

from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.signal import convolve2d

from galaxy.empirical_psf import estimate_empirical_psf


def _synthetic_star_field() -> np.ndarray:
    truth = np.zeros((96, 96), dtype=np.float32)
    for row, col, flux in ((24, 20, 10.0), (48, 60, 8.0), (72, 30, 12.0), (30, 74, 7.0)):
        truth[row, col] = flux
    kernel = np.array(
        [
            [0.01, 0.04, 0.01],
            [0.04, 0.80, 0.04],
            [0.01, 0.04, 0.01],
        ],
        dtype=np.float32,
    )
    return convolve2d(truth, kernel, mode='same', boundary='symm').astype(np.float32)


def test_estimate_empirical_psf_from_array_returns_normalized_kernel_and_smoothed_image() -> None:
    image = _synthetic_star_field()

    result = estimate_empirical_psf(image, kernel_size=9, max_stars=4, threshold_sigma=3.0, presmooth_sigma=0.0)

    assert result.kernel.shape == (9, 9)
    assert result.smoothed_image.shape == image.shape
    assert result.smoothed_image.dtype == np.float32
    assert np.isclose(result.kernel.sum(), 1.0, atol=1e-5)
    center = result.kernel[result.kernel.shape[0] // 2, result.kernel.shape[1] // 2]
    assert center == result.kernel.max()
    assert result.stamp_count >= 3
    assert result.source_path is None


def test_estimate_empirical_psf_accepts_fits_path(tmp_path) -> None:
    image = _synthetic_star_field()
    fits_path = tmp_path / 'stars.fits'
    fits.PrimaryHDU(data=image).writeto(fits_path)

    result = estimate_empirical_psf(fits_path, kernel_size=9, max_stars=4, threshold_sigma=3.0, presmooth_sigma=0.0)

    assert result.source_path == str(fits_path)
    assert result.kernel.shape == (9, 9)
    assert np.isclose(result.kernel.sum(), 1.0, atol=1e-5)


def test_estimate_empirical_psf_raises_when_no_stars_are_found() -> None:
    image = np.zeros((32, 32), dtype=np.float32)

    try:
        estimate_empirical_psf(image, kernel_size=9, threshold_sigma=5.0, presmooth_sigma=0.0)
    except ValueError as exc:
        assert 'no suitable star stamps found' in str(exc)
    else:
        raise AssertionError('expected ValueError when no stars are present')

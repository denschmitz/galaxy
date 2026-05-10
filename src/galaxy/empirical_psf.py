from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from astropy.io import fits
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.signal import convolve2d

from galaxy.fitsio import load_fits_plane


@dataclass(slots=True)
class EmpiricalPSFResult:
    kernel: np.ndarray
    smoothed_image: np.ndarray
    star_positions: list[tuple[int, int]]
    stamp_count: int
    source_path: str | None = None


ArrayLikeImage = np.ndarray | list[list[float]]
ImageSource = str | Path | ArrayLikeImage


def estimate_empirical_psf(
    image_or_path: ImageSource,
    *,
    kernel_size: int = 25,
    max_stars: int = 32,
    threshold_sigma: float = 5.0,
    presmooth_sigma: float = 1.0,
) -> EmpiricalPSFResult:
    if kernel_size < 3 or kernel_size % 2 == 0:
        raise ValueError('kernel_size must be an odd integer >= 3')
    if max_stars < 1:
        raise ValueError('max_stars must be >= 1')
    if threshold_sigma <= 0:
        raise ValueError('threshold_sigma must be > 0')

    image, source_path = _load_image(image_or_path)
    half_size = kernel_size // 2
    filtered = gaussian_filter(image, presmooth_sigma) if presmooth_sigma > 0 else image
    background = float(np.median(filtered))
    sigma = _robust_sigma(filtered)
    threshold = background + threshold_sigma * sigma

    candidates = _find_star_candidates(filtered, threshold, half_size)
    stamps = _extract_star_stamps(image, candidates, kernel_size, max_stars)
    if not stamps:
        raise ValueError('no suitable star stamps found for empirical PSF estimation')

    kernel = _combine_stamps(stamps)
    smoothed_image = convolve2d(image, kernel, mode='same', boundary='symm').astype(np.float32)
    positions = [(row, col) for row, col, _ in stamps]
    return EmpiricalPSFResult(
        kernel=kernel,
        smoothed_image=smoothed_image,
        star_positions=positions,
        stamp_count=len(stamps),
        source_path=source_path,
    )


def _load_image(image_or_path: ImageSource) -> tuple[np.ndarray, str | None]:
    if isinstance(image_or_path, (str, Path)):
        source = Path(image_or_path)
        try:
            plane = load_fits_plane(source)
            return np.asarray(plane.data, dtype=np.float32), str(source)
        except ValueError as exc:
            if 'missing WCS' not in str(exc):
                raise
            with fits.open(source) as hdul:
                for hdu in hdul:
                    if getattr(hdu, 'data', None) is not None:
                        return np.asarray(hdu.data, dtype=np.float32), str(source)
            raise ValueError(f'no image data found in {source}') from exc
    return np.asarray(image_or_path, dtype=np.float32), None


def _robust_sigma(image: np.ndarray) -> float:
    median = float(np.median(image))
    mad = float(np.median(np.abs(image - median)))
    sigma = 1.4826 * mad
    return max(sigma, 1e-6)


def _find_star_candidates(image: np.ndarray, threshold: float, margin: int) -> list[tuple[int, int, float]]:
    local_max = maximum_filter(image, size=3, mode='nearest')
    peaks = np.argwhere((image == local_max) & (image > threshold))
    candidates: list[tuple[int, int, float]] = []
    rows, cols = image.shape
    for row, col in peaks:
        if row < margin or col < margin or row >= rows - margin or col >= cols - margin:
            continue
        candidates.append((int(row), int(col), float(image[row, col])))
    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates


def _extract_star_stamps(
    image: np.ndarray,
    candidates: Iterable[tuple[int, int, float]],
    kernel_size: int,
    max_stars: int,
) -> list[tuple[int, int, np.ndarray]]:
    half_size = kernel_size // 2
    accepted: list[tuple[int, int, np.ndarray]] = []
    exclusion_radius = max(kernel_size, 9)
    for row, col, _ in candidates:
        if any(abs(row - keep_row) < exclusion_radius and abs(col - keep_col) < exclusion_radius for keep_row, keep_col, _ in accepted):
            continue
        stamp = image[row - half_size : row + half_size + 1, col - half_size : col + half_size + 1]
        if stamp.shape != (kernel_size, kernel_size):
            continue
        if not _is_star_like(stamp):
            continue
        accepted.append((row, col, _normalize_stamp(stamp)))
        if len(accepted) >= max_stars:
            break
    return accepted


def _is_star_like(stamp: np.ndarray) -> bool:
    finite = np.nan_to_num(stamp, nan=0.0, posinf=0.0, neginf=0.0)
    if float(finite.max()) <= float(np.median(finite)):
        return False
    if float(finite.sum()) <= 0.0:
        return False
    center = np.array(stamp.shape) // 2
    peak_position = np.unravel_index(int(np.argmax(finite)), finite.shape)
    if max(abs(int(peak_position[0]) - int(center[0])), abs(int(peak_position[1]) - int(center[1]))) > 2:
        return False
    return True


def _normalize_stamp(stamp: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(stamp, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    edge_pixels = np.concatenate([finite[0, :], finite[-1, :], finite[1:-1, 0], finite[1:-1, -1]])
    background = float(np.median(edge_pixels))
    corrected = np.clip(finite - background, 0.0, None)
    total = float(corrected.sum())
    if total <= 0:
        raise ValueError('star stamp normalization produced zero total flux')
    return corrected / total


def _combine_stamps(stamps: list[tuple[int, int, np.ndarray]]) -> np.ndarray:
    stacked = np.stack([stamp for _, _, stamp in stamps], axis=0)
    kernel = np.median(stacked, axis=0).astype(np.float32)
    total = float(kernel.sum())
    if total <= 0:
        raise ValueError('empirical PSF kernel has zero total flux')
    return kernel / total

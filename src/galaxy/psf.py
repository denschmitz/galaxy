from __future__ import annotations

from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
import numpy as np
from scipy.signal import convolve2d

from galaxy.processing_config import PSFConfig
from galaxy.fitsio import FITSPlane


DECONVOLVED_SUFFIX = "__deconvolved"


def apply_presentation_psf(
    planes: dict[str, np.ndarray],
    psf: PSFConfig,
    *,
    pixel_scales_arcsec: dict[str, tuple[float, float]] | None = None,
) -> dict[str, np.ndarray]:
    if not psf.enabled:
        return planes

    resolved = {
        name: _resolve_kernel_spec(
            name,
            psf,
            pixel_scales_arcsec=(pixel_scales_arcsec or {}).get(name),
        )
        for name in planes
    }
    if not any(spec is not None for spec in resolved.values()):
        raise ValueError("psf.enabled requires either common_psf_fwhm_arcsec or an enabled per-plane kernel configuration")

    processed: dict[str, np.ndarray] = {}
    for name, image in planes.items():
        spec = resolved[name]
        if spec is None:
            processed[name] = np.asarray(image, dtype=np.float32)
            continue
        processed[name] = _richardson_lucy(
            np.asarray(image, dtype=np.float32),
            spec["kernel"],
            iterations=spec["iterations"],
            regularization=spec["regularization"],
        )
    return processed


def build_deconvolved_plane_artifacts(planes: list[FITSPlane], psf: PSFConfig, cache_dir: Path) -> list[FITSPlane]:
    if not psf.enabled:
        return []

    resolved = {
        plane.plane_id: _resolve_kernel_spec(plane.plane_id, psf, wcs=plane.wcs)
        for plane in planes
    }
    if not any(spec is not None for spec in resolved.values()):
        raise ValueError(
            "psf.enabled requires a valid kernel for at least one enabled plane in the deconvolved branch"
        )

    processed_planes: list[FITSPlane] = []
    for plane in planes:
        spec = resolved[plane.plane_id]
        processed = (
            np.asarray(plane.data, dtype=np.float32).copy()
            if spec is None
            else _richardson_lucy(
                np.asarray(plane.data, dtype=np.float32),
                spec["kernel"],
                iterations=spec["iterations"],
                regularization=spec["regularization"],
                valid_mask=(
                    np.isfinite(plane.data)
                    if plane.mask is None
                    else np.isfinite(plane.data) & ~np.asarray(plane.mask, dtype=bool)
                ),
            )
        )
        source_path = Path(str(plane.metadata.get("source_path") or cache_dir / f"{plane.plane_id}.fits"))
        destination = cache_dir / f"{source_path.stem}{DECONVOLVED_SUFFIX}.fits"
        metadata = dict(plane.metadata)
        metadata["artifact_branch"] = "deconvolved"
        metadata["psf_processed"] = spec is not None
        metadata["original_source_path"] = str(source_path)
        metadata["source_path"] = str(destination)
        _write_plane_artifact(destination, processed, plane)
        processed_planes.append(
            FITSPlane(
                plane_id=plane.plane_id,
                data=processed,
                wcs=plane.wcs.deepcopy(),
                metadata=metadata,
                mask=None if plane.mask is None else np.asarray(plane.mask, dtype=bool),
            )
        )
    return processed_planes


def _resolve_kernel_spec(
    plane_name: str,
    psf: PSFConfig,
    *,
    wcs: WCS | None = None,
    pixel_scales_arcsec: tuple[float, float] | None = None,
) -> dict[str, object] | None:
    plane_config = psf.per_plane.get(plane_name)
    if plane_config is not None and not plane_config.enabled:
        return None

    kernel = None
    if plane_config is not None and plane_config.kernel_path:
        kernel = _load_kernel(Path(plane_config.kernel_path))
    elif psf.common_psf_fwhm_arcsec is not None:
        scales = pixel_scales_arcsec or _celestial_pixel_scales_arcsec(wcs)
        kernel = _gaussian_kernel_from_fwhm(psf.common_psf_fwhm_arcsec, scales)
    elif plane_config is not None and plane_config.enabled:
        raise ValueError(f"psf enabled for plane '{plane_name}' but no kernel source was configured")

    if kernel is None:
        return None

    return {
        "kernel": kernel,
        "iterations": plane_config.max_iterations if plane_config is not None else 10,
        "regularization": plane_config.regularization if plane_config is not None else 0.0,
    }


def _write_plane_artifact(path: Path, data: np.ndarray, plane: FITSPlane) -> None:
    header = plane.wcs.to_header()
    metadata = dict(plane.metadata)
    if metadata.get("filter") is not None:
        header["FILTER"] = str(metadata["filter"])
    if metadata.get("instrument") is not None:
        header["INSTRUME"] = str(metadata["instrument"])
    if metadata.get("detector") is not None:
        header["DETECTOR"] = str(metadata["detector"])
    if metadata.get("mission") is not None:
        header["TELESCOP"] = str(metadata["mission"])
    if metadata.get("observation_id") is not None:
        header["OBS_ID"] = str(metadata["observation_id"])
    if metadata.get("exposure_time") is not None:
        try:
            header["EXPTIME"] = float(metadata["exposure_time"])
        except (TypeError, ValueError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=np.asarray(data, dtype=np.float32), header=header).writeto(path, overwrite=True)


def _load_kernel(path: Path) -> np.ndarray:
    with fits.open(path) as hdul:
        for hdu in hdul:
            if getattr(hdu, "data", None) is not None:
                return _normalize_kernel(np.asarray(hdu.data, dtype=np.float32))
    raise ValueError(f"no image data found in PSF kernel file: {path}")


def _celestial_pixel_scales_arcsec(wcs: WCS | None) -> tuple[float, float]:
    if wcs is None or not wcs.has_celestial:
        raise ValueError("angular Gaussian PSF requires a two-dimensional celestial WCS or explicit pixel scales")
    celestial = wcs.celestial
    matrix = np.asarray(celestial.pixel_scale_matrix, dtype=np.float64)
    if matrix.shape != (2, 2) or not np.isfinite(matrix).all():
        raise ValueError("angular Gaussian PSF requires finite two-dimensional celestial pixel geometry")
    first, second = matrix[:, 0], matrix[:, 1]
    first_norm, second_norm = float(np.linalg.norm(first)), float(np.linalg.norm(second))
    if first_norm <= 0 or second_norm <= 0:
        raise ValueError("angular Gaussian PSF requires positive celestial pixel scales")
    relative_dot = abs(float(np.dot(first, second))) / (first_norm * second_norm)
    if relative_dot > 1e-6:
        raise ValueError("angular Gaussian PSF does not support skewed celestial pixel geometry")
    scales = np.asarray(proj_plane_pixel_scales(celestial), dtype=np.float64) * 3600.0
    return float(scales[0]), float(scales[1])


def _gaussian_kernel_from_fwhm(
    fwhm_arcsec: float,
    pixel_scales_arcsec: tuple[float, float],
) -> np.ndarray:
    fwhm = float(fwhm_arcsec)
    scales = np.asarray(pixel_scales_arcsec, dtype=np.float64)
    if not np.isfinite(fwhm) or fwhm <= 0:
        raise ValueError("Gaussian PSF FWHM must be finite and positive")
    if scales.shape != (2,) or not np.isfinite(scales).all() or np.any(scales <= 0):
        raise ValueError("Gaussian PSF pixel scales must contain two finite positive values")
    sigma_x, sigma_y = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)) * scales)
    radius_x = max(int(np.ceil(4.0 * sigma_x)), 1)
    radius_y = max(int(np.ceil(4.0 * sigma_y)), 1)
    x_axis = np.arange(-radius_x, radius_x + 1, dtype=np.float64)
    y_axis = np.arange(-radius_y, radius_y + 1, dtype=np.float64)
    xx, yy = np.meshgrid(x_axis, y_axis, indexing="xy")
    kernel = np.exp(-0.5 * ((xx / sigma_x) ** 2 + (yy / sigma_y) ** 2))
    return _normalize_kernel(kernel)


def _normalize_kernel(kernel: np.ndarray) -> np.ndarray:
    values = np.asarray(kernel, dtype=np.float64)
    if values.ndim != 2 or any(size % 2 == 0 for size in values.shape):
        raise ValueError("PSF kernel must be a two-dimensional array with odd dimensions")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("PSF kernel must contain only finite nonnegative values")
    total = float(values.sum(dtype=np.float64))
    if total <= 0:
        raise ValueError("PSF kernel must contain positive values")
    return (values / total).astype(np.float32)


def _richardson_lucy(
    image: np.ndarray,
    kernel: np.ndarray,
    iterations: int,
    regularization: float,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    values = np.asarray(image, dtype=np.float32)
    valid = np.isfinite(values) if valid_mask is None else np.asarray(valid_mask, dtype=bool)
    if valid.shape != values.shape:
        raise ValueError("Richardson-Lucy validity mask must match the image shape")
    valid &= np.isfinite(values)
    if not np.any(valid):
        raise ValueError("Richardson-Lucy input has no finite valid samples")
    if np.any(values[valid] < 0):
        raise ValueError("Richardson-Lucy requires nonnegative valid samples; signed inputs are unsupported")

    mask = valid.astype(np.float32)
    observed = np.where(valid, values, 0.0).astype(np.float32)
    estimate = np.where(valid, np.maximum(observed, 1e-6), 0.0).astype(np.float32)
    normalized_kernel = _normalize_kernel(kernel)
    mirrored = normalized_kernel[::-1, ::-1]
    sensitivity = convolve2d(mask, mirrored, mode="same", boundary="fill", fillvalue=0.0)
    regularization_term = max(float(regularization), 0.0)

    for _ in range(iterations):
        blurred = convolve2d(estimate, normalized_kernel, mode="same", boundary="fill", fillvalue=0.0)
        relative_blur = np.zeros_like(observed)
        relative_blur[valid] = observed[valid] / np.maximum(blurred[valid], 1e-6)
        correction = convolve2d(relative_blur, mirrored, mode="same", boundary="fill", fillvalue=0.0)
        estimate[valid] *= correction[valid] / np.maximum(sensitivity[valid], 1e-6)
        estimate[valid] = np.clip(estimate[valid], 0.0, None)
        estimate[~valid] = 0.0

    if regularization_term > 0:
        blend = regularization_term / (1.0 + regularization_term)
        estimate = estimate * (1.0 - blend) + observed * blend

    estimate[~valid] = 0.0
    return estimate.astype(np.float32)

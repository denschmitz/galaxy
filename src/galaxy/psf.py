from __future__ import annotations

from pathlib import Path

from astropy.io import fits
import numpy as np
from scipy.signal import convolve2d

from galaxy.config import PSFConfig
from galaxy.fitsio import FITSPlane


DECONVOLVED_SUFFIX = "__deconvolved"


def apply_presentation_psf(planes: dict[str, np.ndarray], psf: PSFConfig) -> dict[str, np.ndarray]:
    if not psf.enabled:
        return planes

    resolved = {name: _resolve_kernel_spec(name, psf) for name in planes}
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

    resolved = {plane.plane_id: _resolve_kernel_spec(plane.plane_id, psf) for plane in planes}
    missing = [plane.plane_id for plane in planes if resolved[plane.plane_id] is None]
    if missing:
        raise ValueError(
            "psf.enabled requires a valid kernel for every plane in the deconvolved branch; "
            f"missing kernels for: {', '.join(sorted(missing))}"
        )

    processed_planes: list[FITSPlane] = []
    for plane in planes:
        spec = resolved[plane.plane_id]
        assert spec is not None
        processed = _richardson_lucy(
            np.asarray(plane.data, dtype=np.float32),
            spec["kernel"],
            iterations=spec["iterations"],
            regularization=spec["regularization"],
        )
        source_path = Path(str(plane.metadata.get("source_path") or cache_dir / f"{plane.plane_id}.fits"))
        destination = cache_dir / f"{source_path.stem}{DECONVOLVED_SUFFIX}.fits"
        metadata = dict(plane.metadata)
        metadata["artifact_branch"] = "deconvolved"
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


def _resolve_kernel_spec(plane_name: str, psf: PSFConfig) -> dict[str, object] | None:
    plane_config = psf.per_plane.get(plane_name)
    if plane_config is not None and not plane_config.enabled:
        return None

    kernel = None
    if plane_config is not None and plane_config.kernel_path:
        kernel = _load_kernel(Path(plane_config.kernel_path))
    elif psf.common_psf_fwhm_arcsec is not None:
        kernel = _gaussian_kernel_from_fwhm(psf.common_psf_fwhm_arcsec)
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


def _gaussian_kernel_from_fwhm(fwhm_arcsec: float) -> np.ndarray:
    sigma = max(float(fwhm_arcsec) / 2.355, 0.3)
    radius = max(int(np.ceil(3.0 * sigma)), 1)
    axis = np.arange(-radius, radius + 1, dtype=np.float32)
    xx, yy = np.meshgrid(axis, axis, indexing="xy")
    kernel = np.exp(-0.5 * (xx**2 + yy**2) / (sigma**2))
    return _normalize_kernel(kernel)


def _normalize_kernel(kernel: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(kernel, dtype=np.float32), 0.0, None)
    total = float(clipped.sum())
    if total <= 0:
        raise ValueError("PSF kernel must contain positive values")
    return clipped / total


def _richardson_lucy(
    image: np.ndarray,
    kernel: np.ndarray,
    iterations: int,
    regularization: float,
) -> np.ndarray:
    observed = np.clip(np.nan_to_num(image, nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)
    estimate = np.maximum(observed, 1e-6).astype(np.float32)
    mirrored = kernel[::-1, ::-1]
    regularization_term = max(float(regularization), 0.0)

    for _ in range(iterations):
        blurred = convolve2d(estimate, kernel, mode="same", boundary="symm")
        relative_blur = observed / np.maximum(blurred + regularization_term, 1e-6)
        estimate *= convolve2d(relative_blur, mirrored, mode="same", boundary="symm")
        estimate = np.clip(estimate, 0.0, None)

    if regularization_term > 0:
        blend = regularization_term / (1.0 + regularization_term)
        estimate = estimate * (1.0 - blend) + observed * blend

    return estimate.astype(np.float32)

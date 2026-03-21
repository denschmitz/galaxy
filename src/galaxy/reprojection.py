from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
import numpy as np
from reproject.adaptive.core import _reproject_adaptive_2d
from reproject.interpolation.core import _reproject_full

from galaxy.config import CanvasConfig
from galaxy.fitsio import FITSPlane


MAX_DERIVED_OUTPUT_DIMENSION = 100_000
MEMORY_WARNING_FRACTION = 0.80
REPROJECT_METHOD_ADAPTIVE_FLUX = "adaptive_flux_conserving"
REPROJECT_METHOD_INTERPOLATION = "interpolation"



@dataclass(slots=True)
class ReprojectedPlane:
    plane_id: str
    data: np.ndarray
    footprint: np.ndarray
    metadata: dict[str, object]


def build_output_wcs(canvas: CanvasConfig, resolved_center: SkyCoord) -> tuple[WCS, tuple[int, int]]:
    if canvas.center.mode == "explicit":
        center_ra = canvas.center.ra_deg
        center_dec = canvas.center.dec_deg
    else:
        center_ra = resolved_center.ra.deg
        center_dec = resolved_center.dec.deg

    wcs = WCS(naxis=2)
    pixel_scale = canvas.pixel_scale_arcsec / 3600.0
    rotation = np.deg2rad(canvas.rotation_deg)
    cd = pixel_scale * np.array(
        [
            [-np.cos(rotation), np.sin(rotation)],
            [np.sin(rotation), np.cos(rotation)],
        ]
    )
    wcs.wcs.ctype = [f"RA---{canvas.projection}", f"DEC--{canvas.projection}"]
    wcs.wcs.crval = [center_ra, center_dec]
    wcs.wcs.crpix = [canvas.width / 2.0, canvas.height / 2.0]
    wcs.wcs.cd = cd
    return wcs, (canvas.height, canvas.width)


def derive_reference_output_wcs(
    planes: list[FITSPlane],
    expand_fraction: float = 0.10,
) -> tuple[WCS, tuple[int, int], dict[str, object]]:
    if not planes:
        raise ValueError("cannot derive output WCS without input planes")

    reference = planes[0]
    reference_wcs = reference.wcs.deepcopy()
    min_x, min_y, max_x, max_y = _projected_union_bounds(planes, reference_wcs)

    span_x = max_x - min_x
    span_y = max_y - min_y
    expanded_width = max(int(np.ceil((span_x + 1.0) * (1.0 + expand_fraction))), 1)
    expanded_height = max(int(np.ceil((span_y + 1.0) * (1.0 + expand_fraction))), 1)
    _validate_output_shape(expanded_width, expanded_height, reference.plane_id)

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_ra, center_dec = reference_wcs.pixel_to_world_values(center_x, center_y)

    output_wcs = reference_wcs.deepcopy()
    output_wcs.wcs.crval = [float(center_ra), float(center_dec)]
    output_wcs.wcs.crpix = [expanded_width / 2.0, expanded_height / 2.0]

    pixel_scale_arcsec = float(np.mean(np.abs(proj_plane_pixel_scales(reference_wcs)))) * 3600.0
    diagnostics = {
        "mode": "reference_plane_union",
        "reference_plane_id": reference.plane_id,
        "expand_fraction": expand_fraction,
        "pixel_scale_arcsec": pixel_scale_arcsec,
        "width": expanded_width,
        "height": expanded_height,
    }
    return output_wcs, (expanded_height, expanded_width), diagnostics


def reproject_plane(
    plane: FITSPlane,
    output_wcs: WCS,
    shape_out: tuple[int, int],
    flux_conserving: bool,
) -> ReprojectedPlane:
    if flux_conserving:
        array_out = np.empty(shape_out, dtype=np.float64)
        footprint_out = np.empty(shape_out, dtype=np.float64)
        data, footprint = _reproject_adaptive_2d(
            np.asarray(plane.data, dtype=np.float64),
            plane.wcs,
            output_wcs,
            shape_out=shape_out,
            array_out=array_out,
            output_footprint=footprint_out,
            return_footprint=True,
            conserve_flux=True,
        )
    else:
        array_out = np.empty(shape_out, dtype=np.float32)
        footprint_out = np.empty(shape_out, dtype=np.float32)
        data, footprint = _reproject_full(
            np.asarray(plane.data, dtype=np.float32),
            plane.wcs,
            output_wcs,
            shape_out=shape_out,
            array_out=array_out,
            output_footprint=footprint_out,
            return_footprint=True,
        )
    return ReprojectedPlane(
        plane_id=plane.plane_id,
        data=np.nan_to_num(data.astype(np.float32), nan=0.0),
        footprint=np.nan_to_num(footprint.astype(np.float32), nan=0.0),
        metadata=dict(plane.metadata),
    )


def save_reprojected_plane(plane: ReprojectedPlane, output_wcs: WCS, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / f"{plane.plane_id}.fits"
    footprint_path = directory / f"{plane.plane_id}_footprint.fits"
    fits.PrimaryHDU(data=plane.data, header=output_wcs.to_header()).writeto(image_path, overwrite=True)
    fits.PrimaryHDU(data=plane.footprint, header=output_wcs.to_header()).writeto(footprint_path, overwrite=True)
    return image_path, footprint_path


def reproject_all(
    planes: list[FITSPlane],
    output_wcs: WCS,
    shape_out: tuple[int, int],
    flux_conserving: bool,
    progress: Callable[[str], None] | None = None,
) -> list[ReprojectedPlane]:
    results: list[ReprojectedPlane] = []
    for plane in planes:
        if progress:
            progress(f"Reprojecting {plane.plane_id}")
        results.append(reproject_plane(plane, output_wcs, shape_out, flux_conserving))
    return results


def _projected_union_bounds(planes: list[FITSPlane], reference_wcs: WCS) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for plane in planes:
        height, width = plane.data.shape[-2:]
        corners = np.array(
            [
                (-0.5, -0.5),
                (width - 0.5, -0.5),
                (-0.5, height - 0.5),
                (width - 0.5, height - 0.5),
            ],
            dtype=float,
        )
        ra, dec = plane.wcs.pixel_to_world_values(corners[:, 0], corners[:, 1])
        ref_x, ref_y = reference_wcs.world_to_pixel_values(ra, dec)
        finite = np.isfinite(ref_x) & np.isfinite(ref_y)
        xs.extend(np.asarray(ref_x)[finite].tolist())
        ys.extend(np.asarray(ref_y)[finite].tolist())

    if not xs or not ys:
        raise ValueError("unable to derive finite union bounds from input planes")
    return min(xs), min(ys), max(xs), max(ys)


def estimate_workspace_peak_bytes(
    output_pixel_count: int,
    plane_count: int,
    bytes_per_pixel: int,
    reprojection_method: str,
) -> int:
    pixels = max(int(output_pixel_count), 0)
    stored_plane_bytes = pixels * 8 * max(int(plane_count), 0)
    current_plane_bytes = pixels * max(int(bytes_per_pixel), 0)
    if reprojection_method == REPROJECT_METHOD_ADAPTIVE_FLUX:
        current_plane_bytes += pixels * 8
    composition_bytes = pixels * 20
    return stored_plane_bytes + current_plane_bytes + composition_bytes


def get_system_memory_bytes() -> int | None:
    try:
        import ctypes

        if hasattr(ctypes, "windll"):
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
    except Exception:
        pass

    try:
        import os

        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return int(page_size) * int(page_count)
    except Exception:
        return None


def _validate_output_shape(width: int, height: int, reference_plane_id: str) -> None:
    if width > MAX_DERIVED_OUTPUT_DIMENSION or height > MAX_DERIVED_OUTPUT_DIMENSION:
        raise ValueError(
            "derived workspace is unreasonably large "
            f"({width}x{height} pixels from reference plane '{reference_plane_id}'). "
            "This usually means the selected planes do not share a sane overlapping WCS footprint. "
            "Narrow the selection by mission, instrument, filter, or observation before reprojection."
        )

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

from galaxy.bridge import NativePresentation
from galaxy.processing_config import CanvasConfig
from galaxy.fitsio import FITSPlane, _validated_coverage, validated_grid_identity


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
    wcs: WCS | None = None
    valid: np.ndarray | None = None
    domain: str = "aligned_linear"
    branch: str | None = None
    source_ids: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    grid_id: str | None = None
    presentation_support: np.ndarray | None = None
    estimate_influence: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.data = np.asarray(self.data, dtype=np.float32)
        if self.data.ndim != 2:
            raise ValueError(f"plane '{self.plane_id}' values must be two-dimensional")
        self.footprint = _validated_coverage(self.plane_id, self.footprint, self.data.shape)
        finite = np.isfinite(self.data)
        if self.valid is None:
            self.valid = finite & (self.footprint > 0)
        else:
            self.valid = np.asarray(self.valid, dtype=bool)
            if self.valid.shape != self.data.shape:
                raise ValueError(f"plane '{self.plane_id}' validity must match values")
            if np.any(self.valid & ~finite):
                raise ValueError(f"plane '{self.plane_id}' has nonfinite usable values")
            if np.any(self.valid & (self.footprint <= 0)):
                raise ValueError(f"plane '{self.plane_id}' cannot be valid without coverage")
        self.presentation_support = _validated_coverage(
            self.plane_id,
            self.footprint if self.presentation_support is None else self.presentation_support,
            self.data.shape,
        )
        if self.estimate_influence is None:
            self.estimate_influence = np.zeros(self.data.shape, dtype=bool)
        else:
            raw = np.asarray(self.estimate_influence)
            if raw.shape != self.data.shape or not np.isin(raw, [0, 1]).all():
                raise ValueError(f"plane '{self.plane_id}' estimate influence must be a matching binary mask")
            self.estimate_influence = raw.astype(bool, copy=False)
        usable = self.presentation_valid
        if np.any(self.valid & ~usable):
            raise ValueError(f"plane '{self.plane_id}' observations require presentation support")
        if np.any(self.estimate_influence & ~usable):
            raise ValueError(f"plane '{self.plane_id}' estimate influence requires presentation support")
        self.branch = self.branch or str(self.metadata.get("artifact_branch") or "original")
        self.source_ids = self.source_ids or (str(self.metadata.get("source_path") or self.plane_id),)
        self.grid_id = validated_grid_identity(self.plane_id, self.wcs, self.data.shape, self.grid_id)

    @property
    def coverage(self) -> np.ndarray:
        return self.footprint

    @property
    def presentation_valid(self) -> np.ndarray:
        return np.isfinite(self.data) & (self.presentation_support > 0)

    @property
    def statistics_valid(self) -> np.ndarray:
        return self.valid & ~self.estimate_influence

    @property
    def unit(self) -> str | None:
        value = self.metadata.get("native_unit")
        return None if value is None else str(value)


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


def _resample_values(
    source: np.ndarray, source_wcs: WCS, output_wcs: WCS,
    shape_out: tuple[int, int], flux_conserving: bool, *, scale_flux: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    dtype = np.float64 if flux_conserving else np.float32
    array_out = np.empty(shape_out, dtype=dtype)
    footprint_out = np.empty(shape_out, dtype=dtype)
    options = dict(shape_out=shape_out, array_out=array_out,
                   output_footprint=footprint_out, return_footprint=True)
    if flux_conserving:
        return _reproject_adaptive_2d(
            np.asarray(source, dtype=dtype), source_wcs, output_wcs,
            conserve_flux=scale_flux, **options,
        )
    return _reproject_full(np.asarray(source, dtype=dtype), source_wcs, output_wcs, **options)


def reproject_plane(
    plane: FITSPlane,
    output_wcs: WCS,
    shape_out: tuple[int, int],
    flux_conserving: bool,
    *, presentation: NativePresentation | None = None,
) -> ReprojectedPlane:
    if presentation is not None and presentation.observation is not plane:
        raise ValueError("presentation must belong to the supplied observation plane")
    source_data = np.where(plane.valid, plane.data, np.nan)
    data, footprint = _resample_values(source_data, plane.wcs, output_wcs, shape_out, flux_conserving)
    observed = np.isfinite(data) & np.isfinite(footprint) & (footprint > 0)
    observation_coverage = np.where(observed, footprint, 0).astype(np.float32)
    presentation_coverage = observation_coverage
    influence = np.zeros(shape_out, dtype=bool)
    if presentation is not None and presentation.estimate_mask.any():
        # Keep the observational support and release the unused strict value pass.
        del data, source_data
        data, footprint = _resample_values(
            np.where(presentation.support, presentation.values, np.nan),
            plane.wcs, output_wcs, shape_out, flux_conserving,
        )
        supported = np.isfinite(data) & np.isfinite(footprint) & (footprint > 0)
        presentation_coverage = np.where(supported, footprint, 0).astype(np.float32)
        indicator = np.where(presentation.support, presentation.estimate_mask.astype(np.float32), np.nan)
        projected_indicator, _ = _resample_values(
            indicator, plane.wcs, output_wcs, shape_out, flux_conserving, scale_flux=False,
        )
        influence = supported & np.isfinite(projected_indicator) & (projected_indicator > 0)
    metadata = dict(plane.metadata)
    metadata["valid_coverage_fraction"] = float(np.count_nonzero(observed) / observed.size)
    metadata["support_contract_version"] = 1
    if presentation is not None:
        metadata["bridge"] = presentation.diagnostics.record()
    return ReprojectedPlane(
        plane_id=plane.plane_id,
        data=np.where(np.isfinite(data), data, 0).astype(np.float32),
        footprint=observation_coverage,
        metadata=metadata,
        wcs=output_wcs.deepcopy(), valid=observed,
        presentation_support=presentation_coverage, estimate_influence=influence,
        source_ids=plane.source_ids, parent_ids=(plane.plane_id,),
    )


def save_reprojected_plane(plane: ReprojectedPlane, output_wcs: WCS, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / f"{plane.plane_id}.fits"
    footprint_path = directory / f"{plane.plane_id}_footprint.fits"
    from galaxy.planes import support_hdus, _populate_plane_header
    header = output_wcs.to_header()
    _populate_plane_header(header, plane)
    fits.HDUList([fits.PrimaryHDU(data=plane.data, header=header),
                  *support_hdus(plane, output_wcs)]).writeto(image_path, overwrite=True)
    fits.PrimaryHDU(data=plane.footprint, header=output_wcs.to_header()).writeto(footprint_path, overwrite=True)
    return image_path, footprint_path


def reproject_all(
    planes: list[FITSPlane | NativePresentation],
    output_wcs: WCS,
    shape_out: tuple[int, int],
    flux_conserving: bool,
    progress: Callable[[str], None] | None = None,
) -> list[ReprojectedPlane]:
    results: list[ReprojectedPlane] = []
    for item in planes:
        prepared = item if isinstance(item, NativePresentation) else None
        plane = item.observation if prepared is not None else item
        if progress:
            progress(f"Reprojecting {plane.plane_id}")
        results.append(reproject_plane(plane, output_wcs, shape_out, flux_conserving, presentation=prepared))
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
    *, native_bridge_peak_bytes: int = 0,
) -> int:
    pixels = max(int(output_pixel_count), 0)
    stored_plane_bytes = pixels * 14 * max(int(plane_count), 0)
    current_plane_bytes = pixels * max(int(bytes_per_pixel), 0)
    if reprojection_method == REPROJECT_METHOD_ADAPTIVE_FLUX:
        current_plane_bytes += pixels * 8
    composition_bytes = pixels * 20
    return stored_plane_bytes + current_plane_bytes + composition_bytes + pixels * 40 + max(native_bridge_peak_bytes, 0)


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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from reproject.adaptive.core import _reproject_adaptive_2d
from reproject.interpolation.core import _reproject_full

from galaxy.config import CanvasConfig
from galaxy.fitsio import FITSPlane


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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from astropy.io import fits
import numpy as np

from galaxy.reprojection import ReprojectedPlane


@dataclass(slots=True)
class PlaneRecord:
    plane_id: str
    mission: str | None
    instrument: str | None
    filter_name: str | None
    exposure_time: float | None
    observation_id: str | None
    enabled: bool = True


def build_plane_records(planes: list[ReprojectedPlane], disabled_plane_ids: set[str]) -> list[PlaneRecord]:
    return [
        PlaneRecord(
            plane_id=plane.plane_id,
            mission=_string_or_none(plane.metadata.get("mission")),
            instrument=_string_or_none(plane.metadata.get("instrument")),
            filter_name=_string_or_none(plane.metadata.get("filter")),
            exposure_time=_float_or_none(plane.metadata.get("exposure_time")),
            observation_id=_string_or_none(plane.metadata.get("observation_id")),
            enabled=plane.plane_id not in disabled_plane_ids,
        )
        for plane in planes
    ]


def export_multiplane_fits(planes: list[ReprojectedPlane], output_path: str | Path) -> Path:
    hdus: list[fits.ImageHDU | fits.PrimaryHDU] = [fits.PrimaryHDU()]
    for plane in planes:
        header = fits.Header()
        for key, value in plane.metadata.items():
            if value is None:
                continue
            card_key = str(key).upper()[:8]
            try:
                header[card_key] = value
            except Exception:
                continue
        hdus.append(fits.ImageHDU(data=np.asarray(plane.data, dtype=np.float32), header=header, name=plane.plane_id[:68]))
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList(hdus).writeto(destination, overwrite=True)
    return destination


def load_multiplane_fits(path: str | Path) -> dict[str, np.ndarray]:
    with fits.open(path) as hdul:
        return {
            (hdu.name or f"PLANE{idx}"): np.asarray(hdu.data, dtype=np.float32)
            for idx, hdu in enumerate(hdul[1:], start=1)
            if getattr(hdu, "data", None) is not None
        }


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

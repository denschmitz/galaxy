from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np


@dataclass(slots=True)
class FITSPlane:
    plane_id: str
    data: np.ndarray
    wcs: WCS
    metadata: dict[str, Any]
    mask: np.ndarray | None = None


def load_fits_plane(path: str | Path) -> FITSPlane:
    source = Path(path)
    with fits.open(source) as hdul:
        science_index = _select_science_hdu(hdul)
        science_header = hdul[science_index].header
        primary_header = hdul[0].header if hdul else science_header
        if "CTYPE1" not in science_header or "CTYPE2" not in science_header:
            raise ValueError(f"missing WCS in {source}")
        data = np.asarray(hdul[science_index].data, dtype=np.float32)
        dq_mask = _load_dq_mask(hdul, data.shape)
        metadata = {
            "source_path": str(source),
            "extension": science_index,
            "filter": _header_value(primary_header, science_header, "FILTER", "FILTER1", "FILTER2", "PUPIL"),
            "instrument": _header_value(primary_header, science_header, "INSTRUME"),
            "detector": _header_value(primary_header, science_header, "DETECTOR"),
            "mission": _header_value(primary_header, science_header, "TELESCOP"),
            "observation_id": _header_value(primary_header, science_header, "OBS_ID", "ROOTNAME"),
            "exposure_time": _header_value(primary_header, science_header, "EXPTIME"),
            "header_subset": {
                key: science_header.get(key)
                for key in ["CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]
                if key in science_header
            },
        }
        return FITSPlane(
            plane_id=source.stem,
            data=data,
            wcs=WCS(science_header),
            metadata=metadata,
            mask=dq_mask,
        )


def _select_science_hdu(hdul: fits.HDUList) -> int:
    named = [idx for idx, hdu in enumerate(hdul) if str(hdu.name).upper() in {"SCI", "PRIMARY"} and getattr(hdu, "data", None) is not None]
    if named:
        return named[0]
    with_data = [idx for idx, hdu in enumerate(hdul) if getattr(hdu, "data", None) is not None]
    if not with_data:
        raise ValueError("no image extensions found")
    return with_data[0]


def _load_dq_mask(hdul: fits.HDUList, shape: tuple[int, ...]) -> np.ndarray | None:
    for hdu in hdul:
        if str(hdu.name).upper() == "DQ" and getattr(hdu, "data", None) is not None:
            return np.asarray(hdu.data != 0, dtype=bool)
    return np.zeros(shape, dtype=bool)


def _header_value(primary_header: fits.Header, science_header: fits.Header, *keys: str) -> Any:
    for key in keys:
        if key in science_header and science_header.get(key) is not None:
            return science_header.get(key)
        if key in primary_header and primary_header.get(key) is not None:
            return primary_header.get(key)
    return None

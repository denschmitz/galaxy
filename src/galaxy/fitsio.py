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
        header = hdul[science_index].header
        if "CTYPE1" not in header or "CTYPE2" not in header:
            raise ValueError(f"missing WCS in {source}")
        data = np.asarray(hdul[science_index].data, dtype=np.float32)
        dq_mask = _load_dq_mask(hdul, data.shape)
        metadata = {
            "source_path": str(source),
            "extension": science_index,
            "filter": header.get("FILTER") or header.get("FILTER1") or header.get("PUPIL"),
            "instrument": header.get("INSTRUME"),
            "detector": header.get("DETECTOR"),
            "mission": header.get("TELESCOP"),
            "observation_id": header.get("OBS_ID") or header.get("ROOTNAME"),
            "exposure_time": header.get("EXPTIME"),
            "header_subset": {
                key: header.get(key)
                for key in ["CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]
                if key in header
            },
        }
        return FITSPlane(
            plane_id=source.stem,
            data=data,
            wcs=WCS(header),
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

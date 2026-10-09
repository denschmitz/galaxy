from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    valid: np.ndarray | None = None
    coverage: np.ndarray | None = None
    domain: str = "native_linear"
    branch: str = "original"
    source_ids: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    grid_id: str | None = None

    def __post_init__(self) -> None:
        self.data = np.asarray(self.data, dtype=np.float32)
        if self.data.ndim != 2:
            raise ValueError(f"plane '{self.plane_id}' values must be two-dimensional")
        finite = np.isfinite(self.data)
        if self.valid is None:
            invalid = np.zeros(self.data.shape, dtype=bool) if self.mask is None else np.asarray(self.mask, dtype=bool)
            if invalid.shape != self.data.shape:
                raise ValueError(f"plane '{self.plane_id}' invalid mask must match values")
            self.valid = finite & ~invalid
        else:
            self.valid = np.asarray(self.valid, dtype=bool)
            if self.valid.shape != self.data.shape:
                raise ValueError(f"plane '{self.plane_id}' validity must match values")
            if np.any(self.valid & ~finite):
                raise ValueError(f"plane '{self.plane_id}' has nonfinite usable values")
        self.mask = ~self.valid
        if self.coverage is None:
            self.coverage = self.valid.astype(np.float32)
        else:
            self.coverage = _validated_coverage(self.plane_id, self.coverage, self.data.shape)
        self.source_ids = self.source_ids or (str(self.metadata.get("source_path") or self.plane_id),)
        self.grid_id = validated_grid_identity(self.plane_id, self.wcs, self.data.shape, self.grid_id)

    @property
    def unit(self) -> str | None:
        value = self.metadata.get("native_unit")
        return None if value is None else str(value)


def load_fits_plane(path: str | Path) -> FITSPlane:
    source = Path(path)
    with fits.open(source) as hdul:
        science_index = _select_science_hdu(hdul)
        science_header = hdul[science_index].header
        primary_header = hdul[0].header if hdul else science_header
        if "CTYPE1" not in science_header or "CTYPE2" not in science_header:
            raise ValueError(f"missing WCS in {source}")
        data = np.asarray(hdul[science_index].data, dtype=np.float32)
        validity_mask, mask_sources = _load_validity_mask(hdul, data.shape)
        metadata = {
            "source_path": str(source),
            "extension": science_index,
            "filter": _header_value(primary_header, science_header, "FILTER", "FILTER1", "FILTER2", "PUPIL"),
            "instrument": _header_value(primary_header, science_header, "INSTRUME"),
            "detector": _header_value(primary_header, science_header, "DETECTOR"),
            "mission": _header_value(primary_header, science_header, "TELESCOP"),
            "observation_id": _header_value(primary_header, science_header, "OBS_ID", "ROOTNAME"),
            "exposure_time": _header_value(primary_header, science_header, "EXPTIME"),
            "native_unit": _header_value(primary_header, science_header, "BUNIT"),
            "mask_sources": mask_sources,
            "input_valid_fraction": float(np.count_nonzero(~validity_mask) / validity_mask.size),
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
            mask=validity_mask,
        )


def grid_identity(wcs: WCS, shape: tuple[int, ...]) -> str:
    payload = f"{tuple(int(value) for value in shape)}\n{wcs.to_header(relax=True).tostring(sep='\n')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validated_grid_identity(
    plane_id: str,
    wcs: WCS | None,
    shape: tuple[int, ...],
    declared_grid_id: str | None,
) -> str:
    if wcs is None or wcs.pixel_n_dim != 2 or not wcs.has_celestial:
        raise ValueError(f"plane '{plane_id}' requires a two-dimensional celestial WCS")
    computed_grid_id = grid_identity(wcs, shape)
    if declared_grid_id is not None and declared_grid_id != computed_grid_id:
        raise ValueError(f"plane '{plane_id}' grid identity disagrees with its WCS and shape")
    return computed_grid_id


def _validated_coverage(plane_id: str, coverage: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    result = np.asarray(coverage, dtype=np.float32)
    if result.shape != shape:
        raise ValueError(f"plane '{plane_id}' coverage must match values")
    if not np.isfinite(result).all() or np.any((result < 0) | (result > 1)):
        raise ValueError(f"plane '{plane_id}' coverage must be finite within [0,1]")
    return result


def _select_science_hdu(hdul: fits.HDUList) -> int:
    named = [idx for idx, hdu in enumerate(hdul) if str(hdu.name).upper() in {"SCI", "PRIMARY"} and getattr(hdu, "data", None) is not None]
    if named:
        return named[0]
    with_data = [idx for idx, hdu in enumerate(hdul) if getattr(hdu, "data", None) is not None]
    if not with_data:
        raise ValueError("no image extensions found")
    return with_data[0]


def _load_validity_mask(hdul: fits.HDUList, shape: tuple[int, ...]) -> tuple[np.ndarray, list[str]]:
    invalid = np.zeros(shape, dtype=bool)
    sources: list[str] = []
    for hdu in hdul:
        name = str(hdu.name).upper()
        raw = getattr(hdu, "data", None)
        if raw is None or name not in {"DQ", "WHT", "CTX"}:
            continue
        values = np.asarray(raw)
        if values.shape == shape:
            reduced = values
        elif name == "CTX" and values.ndim > len(shape) and values.shape[-len(shape):] == shape:
            axes = tuple(range(values.ndim - len(shape)))
            reduced = np.any(values != 0, axis=axes)
        else:
            continue
        if name == "DQ":
            invalid |= reduced != 0
        elif name == "WHT":
            invalid |= ~np.isfinite(reduced) | (reduced <= 0)
        else:
            invalid |= reduced == 0
        sources.append(name)
    return invalid, sources


def _header_value(primary_header: fits.Header, science_header: fits.Header, *keys: str) -> Any:
    for key in keys:
        if key in science_header and science_header.get(key) is not None:
            return science_header.get(key)
        if key in primary_header and primary_header.get(key) is not None:
            return primary_header.get(key)
    return None

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
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
    artifact_branch: str | None = "original"
    enabled: bool = True
    bridge: dict[str, object] | None = None
    native_unit: str | None = None
    mask_sources: list[str] | None = None
    valid_coverage_fraction: float | None = None
    normalization_mode: str | None = None
    black_percentile: float | None = None
    white_percentile: float | None = None
    black_point: float | None = None
    white_point: float | None = None
    plane_gain: float | None = None
    rgb_contribution_percent: dict[str, float] | None = None


def build_plane_records(planes: list[ReprojectedPlane], disabled_plane_ids: set[str], artifact_branch: str = "original") -> list[PlaneRecord]:
    return [
        PlaneRecord(
            plane_id=plane.plane_id,
            mission=_string_or_none(plane.metadata.get("mission")),
            instrument=_string_or_none(plane.metadata.get("instrument")),
            filter_name=_string_or_none(plane.metadata.get("filter")),
            exposure_time=_float_or_none(plane.metadata.get("exposure_time")),
            observation_id=_string_or_none(plane.metadata.get("observation_id")),
            artifact_branch=_string_or_none(plane.metadata.get("artifact_branch")) or artifact_branch,
            enabled=plane.plane_id not in disabled_plane_ids,
            bridge=plane.metadata.get("bridge"),
            native_unit=_string_or_none(plane.metadata.get("native_unit")),
            mask_sources=[str(item) for item in plane.metadata.get("mask_sources", [])],
            valid_coverage_fraction=_float_or_none(plane.metadata.get("valid_coverage_fraction")),
        )
        for plane in planes
    ]


SUPPORT_TYPES = ("OBS_SUPPORT", "PRESENT_SUPPORT", "ESTIMATE_INFLUENCE")
AUXILIARY_TYPES = ("FOOTPRINT", "VALIDITY", *SUPPORT_TYPES)


def support_hdus(plane: ReprojectedPlane, wcs: WCS) -> list[fits.ImageHDU]:
    result: list[fits.ImageHDU] = []
    for kind, values, dtype in (
        ("OBS_SUPPORT", plane.valid, np.uint8),
        ("PRESENT_SUPPORT", plane.presentation_support, np.float32),
        ("ESTIMATE_INFLUENCE", plane.estimate_influence, np.uint8),
    ):
        header = wcs.to_header()
        header["GALTYPE"] = kind
        header["PARENT"] = plane.plane_id
        result.append(fits.ImageHDU(data=np.asarray(values, dtype=dtype), header=header,
                                    name=f"{plane.plane_id[:40]}_{kind}"))
    return result


def export_multiplane_fits(
    planes: list[ReprojectedPlane],
    output_path: str | Path,
    output_wcs: WCS | None = None,
) -> Path:
    hdus: list[fits.ImageHDU | fits.PrimaryHDU] = [fits.PrimaryHDU()]
    for plane in planes:
        plane_wcs = output_wcs or plane.wcs
        header = plane_wcs.to_header() if plane_wcs is not None else fits.Header()
        _populate_plane_header(header, plane)
        hdus.append(fits.ImageHDU(data=np.asarray(plane.data, dtype=np.float32), header=header, name=plane.plane_id))
        footprint_header = plane_wcs.to_header() if plane_wcs is not None else fits.Header()
        footprint_header["GALTYPE"] = "FOOTPRINT"
        footprint_header["PARENT"] = plane.plane_id
        hdus.append(fits.ImageHDU(
            data=np.asarray(plane.footprint, dtype=np.float32),
            header=footprint_header,
            name=f"{plane.plane_id[:55]}_COVERAGE",
        ))
        validity_header = plane_wcs.to_header() if plane_wcs is not None else fits.Header()
        validity_header["GALTYPE"] = "VALIDITY"
        validity_header["PARENT"] = plane.plane_id
        hdus.append(fits.ImageHDU(
            data=np.asarray(plane.valid, dtype=np.uint8),
            header=validity_header,
            name=f"{plane.plane_id[:55]}_VALID",
        ))
        hdus.extend(support_hdus(plane, plane_wcs))
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
            and hdu.header.get("GALTYPE") not in AUXILIARY_TYPES
        }


def load_multiplane_records(
    path: str | Path, *, legacy_fallback_wcs: WCS | None = None,
    require_bridge_support: bool = False,
) -> list[ReprojectedPlane]:
    """Load typed aligned planes.

    ``legacy_fallback_wcs`` is an explicit inspection-only adapter for historical
    stacks that predate WCS persistence. Certified checkpoint reuse never supplies
    it and continues to require WCS in the FITS artifact itself.
    """
    records: list[ReprojectedPlane] = []
    with fits.open(path) as hdul:
        footprints = {
            str(hdu.header.get("PARENT")): np.asarray(hdu.data, dtype=np.float32)
            for hdu in hdul[1:]
            if hdu.header.get("GALTYPE") == "FOOTPRINT" and getattr(hdu, "data", None) is not None
        }
        validity = {
            str(hdu.header.get("PARENT")): np.asarray(hdu.data, dtype=bool)
            for hdu in hdul[1:]
            if hdu.header.get("GALTYPE") == "VALIDITY" and getattr(hdu, "data", None) is not None
        }
        supports = {
            kind: {str(hdu.header.get("PARENT")): np.asarray(hdu.data)
                   for hdu in hdul[1:] if hdu.header.get("GALTYPE") == kind and hdu.data is not None}
            for kind in SUPPORT_TYPES
        }
        for idx, hdu in enumerate(hdul[1:], start=1):
            if getattr(hdu, "data", None) is None or hdu.header.get("GALTYPE") in AUXILIARY_TYPES:
                continue
            plane_id = str(hdu.header.get("PLANEID") or hdu.name or f"PLANE{idx}")
            modern = hdu.header.get("SUPVER") == 1
            if modern or require_bridge_support:
                if not modern or any(plane_id not in supports[kind] for kind in SUPPORT_TYPES):
                    raise ValueError(f"plane '{plane_id}' missing certified bridge support; rerun reprojection")
                for kind in ("OBS_SUPPORT", "ESTIMATE_INFLUENCE"):
                    if not np.isin(supports[kind][plane_id], [0, 1]).all():
                        raise ValueError(f"plane '{plane_id}' {kind} must be binary")
                if plane_id not in validity or not np.array_equal(validity[plane_id], supports["OBS_SUPPORT"][plane_id]):
                    raise ValueError(f"plane '{plane_id}' observation support disagrees with validity")
            records.append(
                ReprojectedPlane(
                    plane_id=plane_id,
                    data=np.asarray(hdu.data, dtype=np.float32),
                    footprint=footprints.get(plane_id, np.ones_like(hdu.data, dtype=np.float32)),
                    metadata=_metadata_from_header(hdu.header, plane_id),
                    wcs=(
                        WCS(hdu.header)
                        if "CTYPE1" in hdu.header and "CTYPE2" in hdu.header
                        else legacy_fallback_wcs.deepcopy() if legacy_fallback_wcs is not None
                        else None
                    ),
                    valid=validity.get(plane_id),
                    presentation_support=supports["PRESENT_SUPPORT"].get(plane_id),
                    estimate_influence=supports["ESTIMATE_INFLUENCE"].get(plane_id),
                    domain=str(hdu.header.get("DOMAIN") or "aligned_linear"),
                    branch=str(hdu.header.get("BRANCH") or "original"),
                    source_ids=_header_tuple(hdu.header.get("SRCIDS")),
                    parent_ids=_header_tuple(hdu.header.get("PARIDS")),
                    grid_id=str(hdu.header.get("GRIDID")) if hdu.header.get("GRIDID") else None,
                )
            )
    return records


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


def _populate_plane_header(header: fits.Header, plane: ReprojectedPlane) -> None:
    metadata = dict(plane.metadata)
    header["SUPVER"] = 1
    if metadata.get("bridge") is not None:
        header["BRMETA"] = json.dumps(metadata["bridge"], separators=(",", ":"), allow_nan=False)
    header["PLANEID"] = plane.plane_id
    header["DOMAIN"] = plane.domain
    header["BRANCH"] = str(plane.branch)
    header["GRIDID"] = str(plane.grid_id)
    header["SRCIDS"] = json.dumps(list(plane.source_ids), separators=(",", ":"))
    header["PARIDS"] = json.dumps(list(plane.parent_ids), separators=(",", ":"))
    if metadata.get("filter") is not None:
        header["FILTER"] = str(metadata["filter"])
    if metadata.get("mission") is not None:
        header["MISSION"] = str(metadata["mission"])
    if metadata.get("instrument") is not None:
        header["INSTRUME"] = str(metadata["instrument"])
    if metadata.get("detector") is not None:
        header["DETECTOR"] = str(metadata["detector"])
    if metadata.get("observation_id") is not None:
        header["OBS_ID"] = str(metadata["observation_id"])
    if metadata.get("exposure_time") is not None:
        try:
            header["EXPTIME"] = float(metadata["exposure_time"])
        except (TypeError, ValueError):
            pass
    if metadata.get("native_unit") is not None:
        header["SRCBUNIT"] = str(metadata["native_unit"])
    if metadata.get("mask_sources"):
        header["MASKSRC"] = ",".join(str(item) for item in metadata["mask_sources"])
    if metadata.get("valid_coverage_fraction") is not None:
        header["VALFRAC"] = float(metadata["valid_coverage_fraction"])


def _metadata_from_header(header: fits.Header, plane_id: str) -> dict[str, object]:
    return {
        "plane_id": plane_id,
        "support_contract_version": header.get("SUPVER"),
        "bridge": json.loads(header["BRMETA"]) if header.get("BRMETA") else None,
        "filter": header.get("FILTER"),
        "mission": header.get("MISSION"),
        "instrument": header.get("INSTRUME"),
        "detector": header.get("DETECTOR"),
        "observation_id": header.get("OBS_ID"),
        "artifact_branch": header.get("BRANCH"),
        "exposure_time": header.get("EXPTIME"),
        "native_unit": header.get("SRCBUNIT"),
        "mask_sources": [item for item in str(header.get("MASKSRC") or "").split(",") if item],
        "valid_coverage_fraction": header.get("VALFRAC"),
        "header_subset": {
            key: header.get(key)
            for key in ["CTYPE1", "CTYPE2", "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]
            if key in header
        },
    }


def _header_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid checkpoint lineage header: {exc}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("checkpoint lineage header must contain a JSON string array")
    return tuple(parsed)

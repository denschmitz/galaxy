from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from galaxy.processing_config import (
    BackgroundConfig,
    ResolvedBackgroundPlaneConfig,
    SkyRectangleConfig,
)
from galaxy.reprojection import ReprojectedPlane


BACKGROUND_ALGORITHM_VERSION = "background-pedestal-v1"


class BackgroundSamplingError(ValueError):
    """Raised when a pedestal proposal cannot meet its declared sampling contract."""


@dataclass(frozen=True, slots=True)
class BackgroundProposal:
    resolved_planes: dict[str, ResolvedBackgroundPlaneConfig]
    geometric_mask: np.ndarray
    common_valid_mask: np.ndarray
    exclusion_mask: np.ndarray


@dataclass(frozen=True, slots=True)
class BackgroundApplication:
    planes: list[ReprojectedPlane]
    diagnostics: dict[str, dict[str, Any]]
    stage_record: dict[str, Any] | None


def background_selection_key(planes: list[ReprojectedPlane], config: BackgroundConfig) -> str:
    first = _validate_compatible_planes(planes)
    payload = {
        "algorithm_version": BACKGROUND_ALGORITHM_VERSION,
        "branch": first.branch,
        "grid_id": first.grid_id,
        "planes": [
            {"plane_id": plane.plane_id, "source_ids": list(plane.source_ids)}
            for plane in planes
        ],
        "inclusion_regions": [
            region.model_dump(mode="json") for region in config.inclusion_regions
        ],
        "exclusion_regions": [
            region.model_dump(mode="json") for region in config.exclusion_regions
        ],
        "estimator": config.estimator.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def estimate_background(
    planes: list[ReprojectedPlane], config: BackgroundConfig,
) -> BackgroundProposal:
    if config.mode != "pedestal":
        raise ValueError("background estimation requires pedestal mode")
    if not config.inclusion_regions:
        raise BackgroundSamplingError("background pedestal requires at least one inclusion region")
    geometric, common, exclusion = background_masks(planes, config)
    geometric_count = int(np.count_nonzero(geometric))
    if geometric_count == 0:
        raise BackgroundSamplingError("background regions contain no aligned-grid pixel centers")

    common_count = int(np.count_nonzero(common))
    common_fraction = common_count / geometric_count
    estimator = config.estimator
    if common_count < estimator.minimum_samples:
        raise BackgroundSamplingError(
            f"background common sample count {common_count} is below minimum "
            f"{estimator.minimum_samples}"
        )
    if common_fraction < estimator.minimum_valid_fraction:
        raise BackgroundSamplingError(
            f"background common valid fraction {common_fraction:.6f} is below minimum "
            f"{estimator.minimum_valid_fraction:.6f}"
        )

    key = background_selection_key(planes, config)
    resolved: dict[str, ResolvedBackgroundPlaneConfig] = {}
    for plane in planes:
        values = np.asarray(plane.data, dtype=np.float64)[common]
        retained, median, spread = _sigma_clipped_median(
            values, estimator.clip_sigma, estimator.max_iterations
        )
        sample_count = int(retained.size)
        if sample_count < estimator.minimum_samples:
            raise BackgroundSamplingError(
                f"background plane '{plane.plane_id}' retained {sample_count} samples, below "
                f"minimum {estimator.minimum_samples}"
            )
        resolved[plane.plane_id] = ResolvedBackgroundPlaneConfig(
            selection_key=key,
            branch=plane.branch,
            grid_id=str(plane.grid_id),
            source_ids=list(plane.source_ids),
            unit=plane.unit,
            pedestal=median,
            geometric_sample_count=geometric_count,
            common_valid_count=common_count,
            common_valid_fraction=common_fraction,
            sample_count=sample_count,
            rejected_count=common_count - sample_count,
            median=median,
            robust_spread=spread,
            residual_median=float(np.median(retained - median)),
        )
    return BackgroundProposal(resolved, geometric, common, exclusion)


def background_masks(
    planes: list[ReprojectedPlane], config: BackgroundConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    first = _validate_compatible_planes(planes)
    inclusion = _regions_mask(first, config.inclusion_regions)
    exclusion = _regions_mask(first, config.exclusion_regions)
    geometric = inclusion & ~exclusion
    common = geometric.copy()
    for plane in planes:
        common &= plane.statistics_valid
        common &= np.asarray(plane.coverage, dtype=np.float32) > 0
        common &= np.isfinite(np.asarray(plane.data))
    return geometric, common, exclusion


def apply_background(
    planes: list[ReprojectedPlane], config: BackgroundConfig,
) -> BackgroundApplication:
    if config.mode == "off":
        return BackgroundApplication(list(planes), {}, None)
    first = _validate_compatible_planes(planes)
    expected_key = background_selection_key(planes, config)
    expected_ids = {plane.plane_id for plane in planes}
    branch_records = config.resolved_branches.get(str(first.branch), {})
    if set(branch_records) != expected_ids:
        missing = sorted(expected_ids - set(branch_records))
        extra = sorted(set(branch_records) - expected_ids)
        raise BackgroundSamplingError(
            f"background resolved plane set does not match this branch; missing={missing}, extra={extra}"
        )

    corrected: list[ReprojectedPlane] = []
    diagnostics: dict[str, dict[str, Any]] = {}
    for plane in planes:
        record = branch_records[plane.plane_id]
        if record.selection_key != expected_key:
            raise BackgroundSamplingError(
                f"background plane '{plane.plane_id}' has stale region or estimator identity"
            )
        if record.branch != plane.branch or record.grid_id != plane.grid_id:
            raise BackgroundSamplingError(
                f"background plane '{plane.plane_id}' has stale branch or grid identity"
            )
        if tuple(record.source_ids) != tuple(plane.source_ids):
            raise BackgroundSamplingError(
                f"background plane '{plane.plane_id}' has stale source identity"
            )
        values = np.zeros_like(plane.data, dtype=np.float32)
        valid = np.asarray(plane.valid, dtype=bool)
        usable = plane.presentation_valid
        values[usable] = np.asarray(plane.data, dtype=np.float32)[usable] - np.float32(record.pedestal)
        metadata = dict(plane.metadata)
        metadata.update({
            "background_algorithm": BACKGROUND_ALGORITHM_VERSION,
            "background_pedestal": record.pedestal,
            "background_selection_key": expected_key,
        })
        corrected.append(ReprojectedPlane(
            plane_id=plane.plane_id,
            data=values,
            footprint=np.asarray(plane.coverage, dtype=np.float32).copy(),
            metadata=metadata,
            wcs=plane.wcs.deepcopy() if plane.wcs is not None else None,
            valid=valid.copy(),
            presentation_support=plane.presentation_support.copy(),
            estimate_influence=plane.estimate_influence.copy(),
            domain="aligned_linear",
            branch=plane.branch,
            source_ids=plane.source_ids,
            parent_ids=plane.parent_ids,
            grid_id=plane.grid_id,
        ))
        diagnostics[plane.plane_id] = record.model_dump(mode="json")

    digest = hashlib.sha256()
    for plane in corrected:
        digest.update(plane.plane_id.encode("utf-8"))
        digest.update(np.ascontiguousarray(plane.data).tobytes())
        digest.update(np.ascontiguousarray(plane.valid).tobytes())
    stage_record = {
        "stage_id": "background_pedestal",
        "algorithm_ids": ["BG-PED-001", "NORM-BG-001"],
        "algorithm_versions": {"background_pedestal": BACKGROUND_ALGORITHM_VERSION},
        "parent_ids": [plane.plane_id for plane in planes],
        "source_content_identities": [
            {"source_id": source_id}
            for source_id in dict.fromkeys(source for plane in planes for source in plane.source_ids)
        ],
        "branch": first.branch,
        "input_domain": "aligned_linear",
        "output_domain": "aligned_linear",
        "grid_id": first.grid_id,
        "requested_settings": {
            "mode": config.mode,
            "black_reference_policy": config.black_reference_policy,
            "inclusion_regions": [r.model_dump(mode="json") for r in config.inclusion_regions],
            "exclusion_regions": [r.model_dump(mode="json") for r in config.exclusion_regions],
            "estimator": config.estimator.model_dump(mode="json"),
        },
        "resolved_settings": diagnostics,
        "output_content_identity": {"sha256": digest.hexdigest()},
    }
    return BackgroundApplication(corrected, diagnostics, stage_record)


def write_background_diagnostics(
    proposal: BackgroundProposal, destination: str | Path,
) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "algorithm_version": BACKGROUND_ALGORITHM_VERSION,
        "planes": {
            plane_id: record.model_dump(mode="json")
            for plane_id, record in proposal.resolved_planes.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_background_overlay(proposal: BackgroundProposal, destination: str | Path) -> Path:
    image = background_overlay_array(proposal)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(path)
    return path


def background_overlay_array(proposal: BackgroundProposal) -> np.ndarray:
    image = np.zeros((*proposal.geometric_mask.shape, 3), dtype=np.uint8)
    image[proposal.geometric_mask] = (40, 120, 40)
    image[proposal.common_valid_mask] = (80, 255, 80)
    image[proposal.exclusion_mask] = (255, 64, 64)
    return image


def _validate_compatible_planes(planes: list[ReprojectedPlane]) -> ReprojectedPlane:
    if not planes:
        raise BackgroundSamplingError("background processing requires at least one aligned plane")
    first = planes[0]
    if first.domain != "aligned_linear" or first.wcs is None:
        raise BackgroundSamplingError("background processing requires aligned-linear planes with WCS")
    if any(
        plane.domain != "aligned_linear"
        or plane.wcs is None
        or plane.grid_id != first.grid_id
        or plane.data.shape != first.data.shape
        or plane.branch != first.branch
        for plane in planes
    ):
        raise BackgroundSamplingError("background planes must share one branch and celestial grid")
    return first


def _regions_mask(plane: ReprojectedPlane, regions: list[SkyRectangleConfig]) -> np.ndarray:
    shape = plane.data.shape
    if not regions:
        return np.zeros(shape, dtype=bool)
    yy, xx = np.indices(shape, dtype=np.float64)
    ra, dec = plane.wcs.pixel_to_world_values(xx, yy)
    mask = np.zeros(shape, dtype=bool)
    for region in regions:
        delta_ra = (np.asarray(ra) - region.center_ra_deg + 180.0) % 360.0 - 180.0
        tangent_ra_arcsec = delta_ra * np.cos(np.deg2rad(region.center_dec_deg)) * 3600.0
        delta_dec_arcsec = (np.asarray(dec) - region.center_dec_deg) * 3600.0
        mask |= (
            (np.abs(tangent_ra_arcsec) <= region.width_arcsec / 2.0)
            & (np.abs(delta_dec_arcsec) <= region.height_arcsec / 2.0)
        )
    return mask


def _sigma_clipped_median(
    values: np.ndarray, clip_sigma: float, max_iterations: int,
) -> tuple[np.ndarray, float, float]:
    retained = np.asarray(values, dtype=np.float64)
    if retained.size == 0:
        raise BackgroundSamplingError("background estimator received no samples")
    median = float(np.median(retained))
    spread = float(1.4826 * np.median(np.abs(retained - median)))
    for _ in range(max_iterations):
        if spread == 0.0:
            break
        keep = np.abs(retained - median) <= clip_sigma * spread
        if np.all(keep):
            break
        retained = retained[keep]
        if retained.size == 0:
            raise BackgroundSamplingError("background sigma clipping rejected every sample")
        median = float(np.median(retained))
        spread = float(1.4826 * np.median(np.abs(retained - median)))
    return retained, median, spread

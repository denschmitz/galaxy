from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from galaxy.bridge import ALGORITHM_VERSION as BRIDGE_VERSION, BridgeProfile
from galaxy.cache import sha256_file
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import GalaxyConfig
from galaxy.reprojection import (
    REPROJECT_METHOD_ADAPTIVE_FLUX,
    REPROJECT_METHOD_INTERPOLATION,
    ReprojectedPlane,
)


CHECKPOINT_FORMAT_VERSION = 2
CHECKPOINT_DOCUMENT_TYPE = "galaxy.processing_checkpoint"
CHECKPOINT_STAGE_ID = "aligned_checkpoint"
ALGORITHM_VERSIONS = {
    "native_bridge": BRIDGE_VERSION,
    "aligned_fits": "aligned-fits-v2",
    "checkpoint_manifest": "checkpoint-manifest-v2",
    "fits_validity": "fits-validity-v1",
    "masked_rl": "masked-rl-v1",
    "reproject_adaptive_flux": "reproject-adaptive-flux-v2",
    "reproject_interpolation": "reproject-interpolation-v2",
}


class CheckpointValidationError(ValueError):
    """A checkpoint cannot be certified for strict reuse."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentIdentity(StrictModel):
    source_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GridRecord(StrictModel):
    grid_id: str
    shape: tuple[int, int]
    wcs_header: dict[str, Any]


class PlaneSummary(StrictModel):
    plane_id: str
    domain: str
    branch: str
    unit: str | None
    source_ids: tuple[str, ...]
    parent_ids: tuple[str, ...]
    valid_count: int = Field(ge=0)
    positive_coverage_count: int = Field(ge=0)
    shape: tuple[int, int]
    presentation_count: int = Field(ge=0)
    influenced_count: int = Field(ge=0)
    support_hashes: dict[str, str]


class OutputIdentity(StrictModel):
    byte_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CheckpointManifest(StrictModel):
    document_type: Literal["galaxy.processing_checkpoint"]
    format_version: Literal[2]
    stage_id: Literal["aligned_checkpoint"]
    domain: Literal["aligned_linear"]
    branch: Literal["original", "deconvolved"]
    producer_dependency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_inputs: dict[str, Any]
    parents: tuple[str, ...]
    source_content_identities: tuple[ContentIdentity, ...]
    grid: GridRecord
    planes: tuple[PlaneSummary, ...]
    stage_order: tuple[str, ...]
    algorithm_versions: dict[str, str]
    resolved_settings: dict[str, Any]
    mask_identities: tuple[ContentIdentity, ...]
    kernel_identities: tuple[ContentIdentity, ...]
    output: OutputIdentity


def canonical_json_bytes(value: object) -> bytes:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON: {exc}") from exc
    return payload.encode("utf-8")


def producer_dependency_key(producer_inputs: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(producer_inputs)).hexdigest()


def checkpoint_manifest_path(fits_path: str | Path) -> Path:
    source = Path(fits_path)
    return source.with_suffix(".checkpoint.json")


def build_producer_inputs(
    config: GalaxyConfig,
    source_paths: list[Path],
    branch: Literal["original", "deconvolved"],
    *,
    resolved_center_deg: tuple[float, float],
    source_ids_by_path: dict[Path, str] | None = None,
) -> dict[str, Any]:
    sources = _content_identities(source_paths, source_ids_by_path or {})
    canvas = config.canvas.model_dump(mode="json", exclude={"view_state"}, exclude_none=True)
    canvas["resolved_center_deg"] = [float(resolved_center_deg[0]), float(resolved_center_deg[1])]
    method = (
        REPROJECT_METHOD_ADAPTIVE_FLUX
        if config.canvas.flux_conserving
        else REPROJECT_METHOD_INTERPOLATION
    )
    method_version = (
        ALGORITHM_VERSIONS["reproject_adaptive_flux"]
        if config.canvas.flux_conserving
        else ALGORITHM_VERSIONS["reproject_interpolation"]
    )
    kernels = _kernel_identities(config) if branch == "deconvolved" else []
    native_processing: dict[str, Any] = {}
    if branch == "deconvolved":
        native_processing = {
            "common_psf_fwhm_arcsec": config.psf.common_psf_fwhm_arcsec,
            "per_plane": {
                plane_id: {
                    "enabled": policy.enabled,
                    "max_iterations": policy.max_iterations,
                    "regularization": policy.regularization,
                    "kernel_sha256": next(
                        (item["sha256"] for item in kernels if item["source_id"] == plane_id),
                        None,
                    ),
                }
                for plane_id, policy in sorted(config.psf.per_plane.items())
            },
            "algorithm_version": ALGORITHM_VERSIONS["masked_rl"],
        }
    return {
        "branch": branch,
        "bridge": {"enabled": config.bridge.enabled, **BridgeProfile().identity()},
        "canvas": canvas,
        "enabled_filters": sorted(config.planes.enabled_filters),
        "native_processing": native_processing,
        "native_validity": {
            "algorithm_version": ALGORITHM_VERSIONS["fits_validity"],
            "source_content_identities": sources,
        },
        "reprojection": {"method": method, "algorithm_version": method_version},
        "source_content_identities": sources,
    }


def write_checkpoint_manifest(
    planes: list[ReprojectedPlane],
    fits_path: str | Path,
    producer_inputs: dict[str, Any],
    branch: Literal["original", "deconvolved"],
    *,
    resolved_settings: dict[str, Any],
    destination: str | Path | None = None,
) -> Path:
    source = Path(fits_path)
    if not source.is_file():
        raise FileNotFoundError(f"checkpoint FITS artifact is missing: {source}")
    manifest = _build_manifest(planes, source, producer_inputs, branch, resolved_settings)
    target = Path(destination) if destination is not None else checkpoint_manifest_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(manifest.model_dump(mode="json")) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def load_validated_checkpoint(
    fits_path: str | Path,
    manifest_path: str | Path,
    requested_producer_inputs: dict[str, Any],
    branch: Literal["original", "deconvolved"],
) -> tuple[CheckpointManifest, list[ReprojectedPlane]]:
    fits_source = Path(fits_path)
    manifest_source = Path(manifest_path)
    if not manifest_source.is_file():
        raise CheckpointValidationError(
            f"missing checkpoint manifest: {manifest_source}; run full or reprojection-only processing"
        )
    try:
        manifest = CheckpointManifest.model_validate_json(manifest_source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CheckpointValidationError(f"invalid checkpoint manifest: {exc}") from exc
    if manifest.branch != branch:
        raise CheckpointValidationError(
            f"checkpoint branch mismatch: requested {branch}, manifest contains {manifest.branch}"
        )
    stored_key = producer_dependency_key(manifest.producer_inputs)
    if stored_key != manifest.producer_dependency_key:
        raise CheckpointValidationError("checkpoint manifest has a self-inconsistent producer dependency key")
    requested_key = producer_dependency_key(requested_producer_inputs)
    if requested_key != manifest.producer_dependency_key:
        raise CheckpointValidationError(
            "checkpoint producer dependency mismatch; run full or reprojection-only processing"
        )
    if not fits_source.is_file():
        raise CheckpointValidationError(f"checkpoint FITS artifact is missing: {fits_source}")
    if fits_source.stat().st_size != manifest.output.byte_count:
        raise CheckpointValidationError("checkpoint FITS byte count does not match the manifest")
    if sha256_file(fits_source) != manifest.output.sha256:
        raise CheckpointValidationError("checkpoint FITS integrity digest does not match the manifest")
    try:
        planes = load_multiplane_records(fits_source, require_bridge_support=True)
    except Exception as exc:
        raise CheckpointValidationError(f"checkpoint FITS cannot be loaded: {exc}") from exc
    actual_summaries = tuple(_plane_summary(plane) for plane in planes)
    if actual_summaries != manifest.planes:
        raise CheckpointValidationError("checkpoint plane, geometry, lineage, or support summary mismatch")
    if not planes or any(plane.grid_id != manifest.grid.grid_id for plane in planes):
        raise CheckpointValidationError("checkpoint grid identity does not match the manifest")
    return manifest, planes


def read_checkpoint_manifest(path: str | Path) -> CheckpointManifest:
    source = Path(path)
    try:
        return CheckpointManifest.model_validate_json(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CheckpointValidationError(f"invalid checkpoint manifest: {exc}") from exc


def checkpoint_stage_record(manifest: CheckpointManifest) -> dict[str, Any]:
    return {
        "stage_id": manifest.stage_id,
        "algorithm_ids": list(manifest.stage_order),
        "algorithm_versions": dict(manifest.algorithm_versions),
        "parent_ids": list(manifest.parents),
        "source_content_identities": [
            identity.model_dump(mode="json") for identity in manifest.source_content_identities
        ],
        "branch": manifest.branch,
        "input_domain": "native_linear",
        "output_domain": manifest.domain,
        "grid_id": manifest.grid.grid_id,
        "requested_settings": manifest.producer_inputs,
        "resolved_settings": manifest.resolved_settings,
        "output_content_identity": manifest.output.model_dump(mode="json"),
    }


def _build_manifest(
    planes: list[ReprojectedPlane],
    fits_path: Path,
    producer_inputs: dict[str, Any],
    branch: Literal["original", "deconvolved"],
    resolved_settings: dict[str, Any],
) -> CheckpointManifest:
    if not planes:
        raise ValueError("checkpoint requires at least one aligned plane")
    if any(plane.domain != "aligned_linear" for plane in planes):
        raise ValueError("checkpoint requires aligned_linear planes")
    if any(plane.branch != branch for plane in planes):
        raise ValueError(f"checkpoint planes must all use the {branch} branch")
    first = planes[0]
    if first.wcs is None:
        raise ValueError("checkpoint requires celestial WCS")
    if any(plane.grid_id != first.grid_id or plane.data.shape != first.data.shape for plane in planes):
        raise ValueError("checkpoint planes must share one grid")
    source_identities = tuple(
        ContentIdentity.model_validate(item)
        for item in producer_inputs.get("source_content_identities", [])
    )
    kernel_identities = tuple(
        ContentIdentity.model_validate(item)
        for item in _kernel_records_from_inputs(producer_inputs)
    )
    parent_ids = tuple(dict.fromkeys(parent for plane in planes for parent in plane.parent_ids))
    stage_order = ("fits_ingestion", "reprojection", "aligned_fits")
    if branch == "deconvolved":
        stage_order = ("fits_ingestion", "masked_richardson_lucy", "reprojection", "aligned_fits")
    stage_order = (*stage_order[:-2], "native_presentation_bridge", *stage_order[-2:])
    return CheckpointManifest(
        document_type=CHECKPOINT_DOCUMENT_TYPE,
        format_version=CHECKPOINT_FORMAT_VERSION,
        stage_id=CHECKPOINT_STAGE_ID,
        domain="aligned_linear",
        branch=branch,
        producer_dependency_key=producer_dependency_key(producer_inputs),
        producer_inputs=producer_inputs,
        parents=parent_ids,
        source_content_identities=source_identities,
        grid=GridRecord(
            grid_id=str(first.grid_id),
            shape=(int(first.data.shape[0]), int(first.data.shape[1])),
            wcs_header=dict(first.wcs.to_header(relax=True)),
        ),
        planes=tuple(_plane_summary(plane) for plane in planes),
        stage_order=stage_order,
        algorithm_versions=dict(ALGORITHM_VERSIONS),
        resolved_settings=resolved_settings,
        mask_identities=source_identities,
        kernel_identities=kernel_identities,
        output=OutputIdentity(byte_count=fits_path.stat().st_size, sha256=sha256_file(fits_path)),
    )


def _plane_summary(plane: ReprojectedPlane) -> PlaneSummary:
    valid = np.asarray(plane.valid, dtype=bool)
    coverage = np.asarray(plane.coverage, dtype=np.float32)
    return PlaneSummary(
        plane_id=plane.plane_id,
        domain=plane.domain,
        branch=str(plane.branch),
        unit=plane.unit,
        source_ids=tuple(plane.source_ids),
        parent_ids=tuple(plane.parent_ids),
        valid_count=int(np.count_nonzero(valid)),
        positive_coverage_count=int(np.count_nonzero(coverage > 0)),
        shape=(int(plane.data.shape[0]), int(plane.data.shape[1])),
        presentation_count=int(np.count_nonzero(plane.presentation_valid)),
        influenced_count=int(np.count_nonzero(plane.estimate_influence)),
        support_hashes={key: hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
                        for key, array in (("observation", plane.valid),
                                           ("presentation", plane.presentation_support),
                                           ("influence", plane.estimate_influence))},
    )


def _content_identities(
    paths: list[Path], source_ids_by_path: dict[Path, str]
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in paths:
        digest = sha256_file(path)
        source_id = source_ids_by_path.get(path.resolve(), f"sha256:{digest}")
        records.append({"source_id": source_id, "sha256": digest})
    return sorted(records, key=lambda item: item["source_id"])


def _kernel_identities(config: GalaxyConfig) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for plane_id, policy in sorted(config.psf.per_plane.items()):
        if not policy.enabled or policy.kernel_path is None:
            continue
        path = Path(policy.kernel_path)
        if not path.is_file():
            raise FileNotFoundError(f"PSF kernel is missing: {path}")
        records.append({"source_id": plane_id, "sha256": sha256_file(path)})
    return records


def _kernel_records_from_inputs(producer_inputs: dict[str, Any]) -> list[dict[str, str]]:
    native = producer_inputs.get("native_processing")
    if not isinstance(native, dict):
        return []
    per_plane = native.get("per_plane")
    if not isinstance(per_plane, dict):
        return []
    return [
        {"source_id": str(plane_id), "sha256": str(settings["kernel_sha256"])}
        for plane_id, settings in sorted(per_plane.items())
        if isinstance(settings, dict) and settings.get("kernel_sha256")
    ]

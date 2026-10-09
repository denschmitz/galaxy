from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(slots=True)
class CandidateRecord:
    candidate_id: str
    obsid: str | None
    obs_id: str | None
    product_filename: str | None
    data_uri: str | None
    mission: str | None
    instrument: str | None
    detector: str | None
    filter_name: str | None
    product_type: str | None
    product_version: str | None
    observation_date_start: str | None
    observation_date_end: str | None
    exposure_time: float | None
    file_size: int | None
    proposal_id: str | None
    proposal_title: str | None
    target_name: str | None
    selection_rank: list[Any]
    auto_selected: bool = False
    auto_selection_reason: str = "dropped:not_evaluated"
    user_selected: bool | None = None
    selected: bool = False
    selected_reason: str = "dropped:not_evaluated"
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_tokens(self) -> set[str]:
        tokens = {
            str(self.candidate_id).lower(),
            str(self.product_filename or "").lower(),
            str(self.data_uri or "").lower(),
        }
        return {token for token in tokens if token}

    def to_dict(self) -> dict[str, Any]:
        payload = _json_safe(asdict(self))
        payload["filter"] = payload.pop("filter_name")
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateRecord":
        data = dict(payload)
        if "filter_name" not in data:
            data["filter_name"] = data.pop("filter", None)
        data.setdefault("extra_metadata", {})
        data.setdefault("auto_selected", False)
        data.setdefault("auto_selection_reason", "dropped:not_evaluated")
        data.setdefault("user_selected", None)
        data.setdefault("selected", False)
        data.setdefault("selected_reason", data["auto_selection_reason"])
        return cls(**data)


@dataclass(slots=True)
class SelectionInputs:
    include_filters: set[str] = field(default_factory=set)
    include_instruments: set[str] = field(default_factory=set)
    include_missions: set[str] = field(default_factory=set)
    include_obsids: set[str] = field(default_factory=set)
    exclude_obsids: set[str] = field(default_factory=set)
    include_products: set[str] = field(default_factory=set)
    exclude_products: set[str] = field(default_factory=set)
    strategy: str | None = None
    max_per_filter: int | None = None
    max_total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_filters": sorted(self.include_filters),
            "include_instruments": sorted(self.include_instruments),
            "include_missions": sorted(self.include_missions),
            "include_obsids": sorted(self.include_obsids),
            "exclude_obsids": sorted(self.exclude_obsids),
            "include_products": sorted(self.include_products),
            "exclude_products": sorted(self.exclude_products),
            "strategy": self.strategy,
            "max_per_filter": self.max_per_filter,
            "max_total": self.max_total,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SelectionInputs":
        data = payload or {}
        return cls(
            include_filters={str(item).upper() for item in data.get("include_filters", [])},
            include_instruments={str(item).upper() for item in data.get("include_instruments", [])},
            include_missions={str(item).upper() for item in data.get("include_missions", [])},
            include_obsids={str(item) for item in data.get("include_obsids", [])},
            exclude_obsids={str(item) for item in data.get("exclude_obsids", [])},
            include_products={str(item).lower() for item in data.get("include_products", [])},
            exclude_products={str(item).lower() for item in data.get("exclude_products", [])},
            strategy=data.get("strategy"),
            max_per_filter=data.get("max_per_filter"),
            max_total=data.get("max_total"),
        )


@dataclass(slots=True)
class CandidateManifest:
    generated_at: str
    config_path: str | None
    selection_policy: str
    max_observations_per_filter: int
    candidates: list[CandidateRecord]
    selection_inputs: SelectionInputs = field(default_factory=SelectionInputs)
    selection_mode: str = "one_per_filter"
    mission_scope: str = "all"
    recommendation_mode: str = "one_per_filter"

    def __post_init__(self) -> None:
        modes = {"preview_set", "one_per_filter", "custom"}
        scopes = {"all", "hst", "jwst"}
        if self.selection_mode not in modes:
            raise ValueError(f"unknown selection mode: {self.selection_mode}")
        if self.recommendation_mode not in modes - {"custom"}:
            raise ValueError(f"unknown recommendation mode: {self.recommendation_mode}")
        if self.mission_scope not in scopes:
            raise ValueError(f"unknown mission scope: {self.mission_scope}")
        self.candidates = consolidate_candidates(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "generated_at": self.generated_at,
                "config_path": self.config_path,
                "selection_policy": self.selection_policy,
                "max_observations_per_filter": self.max_observations_per_filter,
                "selection_inputs": self.selection_inputs.to_dict(),
                "selection_mode": self.selection_mode,
                "mission_scope": self.mission_scope,
                "recommendation_mode": self.recommendation_mode,
                "candidates": [candidate.to_dict() for candidate in self.candidates],
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateManifest":
        return cls(
            generated_at=str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()),
            config_path=payload.get("config_path"),
            selection_policy=str(payload.get("selection_policy") or "all"),
            max_observations_per_filter=int(payload.get("max_observations_per_filter") or 1),
            selection_inputs=SelectionInputs.from_dict(payload.get("selection_inputs")),
            selection_mode=str(payload.get("selection_mode") or (
                "custom" if payload.get("selection_policy") == "all" else "one_per_filter"
            )),
            mission_scope=str(payload.get("mission_scope") or "all"),
            recommendation_mode=str(payload.get("recommendation_mode") or "one_per_filter"),
            candidates=consolidate_candidates(
                [CandidateRecord.from_dict(item) for item in payload.get("candidates", [])]
            ),
        )


def authoritative_candidate_identity(candidate: CandidateRecord) -> str:
    """Return the normalized downloadable-product identity used across the UI."""
    data_uri = str(candidate.data_uri or "").strip().casefold()
    if data_uri:
        return f"uri:{data_uri}"
    archive = str(candidate.extra_metadata.get("archive") or candidate.mission or "MAST")
    product_id = str(
        candidate.extra_metadata.get("scene_product_id")
        or candidate.product_filename
        or candidate.candidate_id
    )
    return f"product:{archive.strip().casefold()}:{product_id.strip().casefold()}"


def consolidate_candidates(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    """Collapse duplicate archive rows and expose disagreeing ranking metadata."""
    groups: dict[str, list[CandidateRecord]] = {}
    for candidate in candidates:
        groups.setdefault(authoritative_candidate_identity(candidate), []).append(candidate)
    result: list[CandidateRecord] = []
    conflict_fields = (
        "obsid", "obs_id", "product_filename", "mission", "instrument", "detector",
        "filter_name", "product_type", "product_version", "observation_date_start",
        "observation_date_end", "exposure_time", "file_size", "proposal_id",
        "proposal_title", "target_name",
    )
    for identity in sorted(groups):
        records = sorted(groups[identity], key=lambda item: (item.candidate_id, str(item.product_filename or "")))
        merged = CandidateRecord.from_dict(records[0].to_dict())
        if len(records) == 1 and merged.extra_metadata.get("authoritative_identity") == identity:
            result.append(merged)
            continue
        conflicts: dict[str, list[Any]] = {}
        for field_name in conflict_fields:
            values = {_stable_value(getattr(item, field_name)) for item in records if getattr(item, field_name) is not None}
            if len(values) > 1:
                conflicts[field_name] = [_json_safe(json.loads(value)) for value in sorted(values)]
                setattr(merged, field_name, None)
        raw_products = [
            item.extra_metadata.get("raw_product") for item in records
            if isinstance(item.extra_metadata.get("raw_product"), dict)
        ]
        merged.extra_metadata = dict(merged.extra_metadata)
        merged.extra_metadata["authoritative_identity"] = identity
        merged.extra_metadata["source_row_count"] = len(records)
        if raw_products:
            merged.extra_metadata["source_records"] = raw_products
        if conflicts:
            merged.extra_metadata["metadata_conflicts"] = conflicts
        merged.auto_selected = any(item.auto_selected for item in records)
        user_values = {item.user_selected for item in records}
        merged.user_selected = True if True in user_values else (False if user_values == {False} else None)
        merged.selected = any(item.selected for item in records)
        result.append(merged)
    return result


def _stable_value(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


def write_candidate_manifest(manifest: CandidateManifest, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")


def load_candidate_manifest(path: str | Path) -> CandidateManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CandidateManifest.from_dict(payload)


def _json_safe(value: Any) -> Any:
    if np.ma.is_masked(value):
        if isinstance(value, np.ma.MaskedArray) and getattr(value, "ndim", 0) > 0:
            return [_json_safe(item) for item in value.tolist()]
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    return value

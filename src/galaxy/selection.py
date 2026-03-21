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

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "generated_at": self.generated_at,
                "config_path": self.config_path,
                "selection_policy": self.selection_policy,
                "max_observations_per_filter": self.max_observations_per_filter,
                "selection_inputs": self.selection_inputs.to_dict(),
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
            candidates=[CandidateRecord.from_dict(item) for item in payload.get("candidates", [])],
        )


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

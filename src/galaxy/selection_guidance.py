from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mast import apply_selection_policy
from .processing_config import SearchConfig
from .selection import (
    CandidateManifest, CandidateRecord, SelectionInputs, consolidate_candidates,
)


SELECTION_MODES = {
    "preview_set": "Preview set (up to 3 products)",
    "one_per_filter": "Full filter set (one per instrument/filter)",
    "custom": "Custom selection",
}
MISSION_SCOPES = {"all": "All available", "hst": "HST only", "jwst": "JWST only"}


@dataclass(frozen=True, slots=True)
class SelectionSummary:
    mode_label: str
    available_products: int
    selected_products: int
    selected_groups: int
    filter_count: int
    mission_count: int
    instrument_count: int
    known_download_bytes: int
    unknown_size_products: int


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    key: tuple[str, str, str]
    recommended: CandidateRecord
    alternatives: tuple[CandidateRecord, ...]
    selected_count: int


def apply_selection_mode(
    manifest: CandidateManifest, mode: str, scope: str,
) -> CandidateManifest:
    if mode not in SELECTION_MODES:
        raise ValueError(f"unknown selection mode: {mode}")
    if scope not in MISSION_SCOPES:
        raise ValueError(f"unknown mission scope: {scope}")
    candidates = [CandidateRecord.from_dict(item.to_dict()) for item in consolidate_candidates(manifest.candidates)]
    allowed = set() if scope == "all" else {scope.upper()}
    if mode == "custom":
        for candidate in candidates:
            if candidate.user_selected is None:
                candidate.user_selected = candidate.selected
            candidate.selected = bool(candidate.user_selected) and _in_scope(candidate, allowed)
            candidate.selected_reason = (
                "selected:user_manifest" if candidate.selected else "dropped:user_manifest"
            )
    else:
        for candidate in candidates:
            candidate.user_selected = None
        inputs = SelectionInputs.from_dict(manifest.selection_inputs.to_dict())
        inputs.strategy = manifest.selection_policy
        inputs.max_per_filter = 1
        inputs.max_total = 3 if mode == "preview_set" else None
        inputs.include_missions = allowed
        search = SearchConfig(
            observation_selection=manifest.selection_policy,
            max_observations_per_filter=1,
        )
        candidates = apply_selection_policy(candidates, search, inputs)
        candidates = _bound_guided_selection(candidates, mode)
    return CandidateManifest(
        generated_at=manifest.generated_at,
        config_path=manifest.config_path,
        selection_policy=manifest.selection_policy,
        max_observations_per_filter=manifest.max_observations_per_filter,
        selection_inputs=manifest.selection_inputs,
        selection_mode=mode,
        mission_scope=scope,
        recommendation_mode=mode if mode != "custom" else manifest.recommendation_mode,
        candidates=candidates,
    )


def clear_selection(manifest: CandidateManifest) -> CandidateManifest:
    cleared = [CandidateRecord.from_dict(item.to_dict()) for item in manifest.candidates]
    for candidate in cleared:
        candidate.user_selected = False
        candidate.selected = False
        candidate.selected_reason = "dropped:user_manifest"
    return CandidateManifest(
        generated_at=manifest.generated_at,
        config_path=manifest.config_path,
        selection_policy=manifest.selection_policy,
        max_observations_per_filter=manifest.max_observations_per_filter,
        selection_inputs=manifest.selection_inputs,
        selection_mode="custom",
        mission_scope=manifest.mission_scope,
        recommendation_mode=manifest.recommendation_mode,
        candidates=cleared,
    )


def grouped_candidates(manifest: CandidateManifest) -> tuple[CandidateGroup, ...]:
    groups: dict[tuple[str, str, str], list[CandidateRecord]] = {}
    for candidate in consolidate_candidates(manifest.candidates):
        key = (
            str(candidate.mission or "unknown"),
            str(candidate.instrument or "unknown"),
            str(candidate.filter_name or "unknown"),
        )
        groups.setdefault(key, []).append(candidate)
    result: list[CandidateGroup] = []
    for key in sorted(groups, key=lambda item: tuple(value.casefold() for value in item)):
        ordered = sorted(groups[key], key=_recommendation_key)
        recommended = next((item for item in ordered if item.auto_selected), ordered[0])
        alternatives = tuple(item for item in ordered if item.candidate_id != recommended.candidate_id)
        result.append(CandidateGroup(
            key=key,
            recommended=recommended,
            alternatives=alternatives,
            selected_count=sum(1 for item in ordered if item.selected),
        ))
    return tuple(result)


def selection_summary(manifest: CandidateManifest) -> SelectionSummary:
    candidates = consolidate_candidates(manifest.candidates)
    selected = [item for item in candidates if item.selected]
    selected_groups = {
        (item.mission or "unknown", item.instrument or "unknown", item.filter_name or "unknown")
        for item in selected
    }
    return SelectionSummary(
        mode_label=SELECTION_MODES[manifest.selection_mode],
        available_products=len(candidates),
        selected_products=len(selected),
        selected_groups=len(selected_groups),
        filter_count=len({item.filter_name or "unknown" for item in selected}),
        mission_count=len({item.mission or "unknown" for item in selected}),
        instrument_count=len({item.instrument or "unknown" for item in selected}),
        known_download_bytes=sum(item.file_size or 0 for item in selected),
        unknown_size_products=sum(1 for item in selected if item.file_size is None),
    )


def recommendation_explanation(candidate: CandidateRecord) -> str:
    status = "Recommended" if candidate.auto_selected else (
        "Selected by user" if candidate.user_selected else "Alternative"
    )
    facts: list[str] = []
    conflicts = candidate.extra_metadata.get("metadata_conflicts", {})
    raw = candidate.extra_metadata.get("raw_product", {})
    try:
        calibration_level = int(raw.get("calib_level")) if isinstance(raw, dict) else None
    except (TypeError, ValueError):
        calibration_level = None
    if calibration_level is not None and calibration_level >= 3:
        facts.append(f"Level {calibration_level} combined image")
    elif candidate.product_version:
        facts.append(str(candidate.product_version))
    if "exposure_time" in conflicts:
        facts.append("exposure metadata conflicting")
    elif candidate.auto_selection_reason == "selected:deepest_per_filter":
        facts.append(f"deepest known {candidate.filter_name or 'filter'}")
    elif candidate.auto_selection_reason == "selected:latest_per_filter":
        facts.append("latest observation")
    elif candidate.exposure_time is None:
        facts.append("exposure unknown")
    if candidate.exposure_time is not None and "exposure_time" not in conflicts:
        facts.append(f"{candidate.exposure_time:g} s exposure")
    facts.append(_format_size(candidate.file_size))
    if conflicts and "exposure_time" not in conflicts:
        facts.append("archive metadata conflicting")
    return " · ".join([status, *facts[:4]])

def set_custom_selection(
    manifest: CandidateManifest, selected_ids: set[str],
) -> CandidateManifest:
    custom = apply_selection_mode(manifest, "custom", manifest.mission_scope)
    for candidate in custom.candidates:
        candidate.user_selected = candidate.candidate_id in selected_ids
        candidate.selected = candidate.user_selected and _in_scope(
            candidate, set() if custom.mission_scope == "all" else {custom.mission_scope.upper()}
        )
        candidate.selected_reason = (
            "selected:user_manifest" if candidate.selected else "dropped:user_manifest"
        )
    return custom


def _bound_guided_selection(
    candidates: list[CandidateRecord], mode: str,
) -> list[CandidateRecord]:
    selected_by_group: dict[tuple[str, str, str], list[CandidateRecord]] = {}
    for candidate in candidates:
        if not candidate.selected:
            continue
        key = (
            str(candidate.mission or "unknown").casefold(),
            str(candidate.instrument or "unknown").casefold(),
            str(candidate.filter_name or "unknown").casefold(),
        )
        selected_by_group.setdefault(key, []).append(candidate)
    chosen: list[CandidateRecord] = []
    for key in sorted(selected_by_group):
        ranked = sorted(
            selected_by_group[key],
            key=lambda item: (
                0 if item.selected_reason == "selected:explicit_include" else 1,
                _recommendation_key(item),
            ),
        )
        chosen.append(ranked[0])
    if mode == "preview_set":
        chosen = sorted(chosen, key=_recommendation_key)[:3]
    chosen_ids = {item.candidate_id for item in chosen}
    for candidate in candidates:
        if candidate.selected and candidate.candidate_id not in chosen_ids:
            candidate.selected = False
            candidate.selected_reason = "dropped:guided_mode_bound"
    return candidates


def _in_scope(candidate: CandidateRecord, allowed: set[str]) -> bool:
    return not allowed or str(candidate.mission or "").upper() in allowed


def _recommendation_key(candidate: CandidateRecord) -> tuple[Any, ...]:
    exposure = candidate.exposure_time
    return (
        0 if candidate.auto_selected else 1,
        0 if exposure is not None else 1,
        -(float(exposure) if exposure is not None else 0.0),
        tuple(str(item) for item in candidate.selection_rank),
        candidate.candidate_id,
    )


def _format_size(value: int | None) -> str:
    if value is None:
        return "size unknown"
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"






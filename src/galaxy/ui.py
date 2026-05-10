from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
import yaml

from galaxy.config import (
    GalaxyConfig,
    MappingConfig,
    MappingDefaults,
    PlaneMappingConfig,
    RGBMixConfig,
    SearchConfig,
    StretchConfig,
    ToneConfig,
    ToneGainBias,
    TonePercentiles,
    ToneStretchSet,
    dump_config,
    load_config,
)
from galaxy.mast import apply_selection_policy, build_candidate_manifest, discover_candidates
from galaxy.mapping import CompositionInputs, compose_channels, default_plane_mappings
from galaxy.pipeline import run_pipeline
from galaxy.planes import load_multiplane_records
from galaxy.selection import CandidateManifest, SelectionInputs, load_candidate_manifest
from galaxy.targeting import region_to_mast_shape, resolve_target
from galaxy.tone import apply_tone


DISCOVERY_CACHE_MAX_AGE = timedelta(days=183)
PREVIEW_BRANCH_FILE_NAMES = {
    "original": "exported_planes.fits",
    "deconvolved": "exported_planes_deconvolved.fits",
}
PROJECT_FILE_NAMES = ("project.yaml",)



def main() -> None:
    st.set_page_config(page_title="Galaxy", layout="wide")
    input_path = _resolve_input_path()
    if not input_path:
        st.error("Provide a config YAML, candidate manifest JSON, or multi-plane FITS path as an argument.")
        return

    if input_path.suffix.lower() in {".yaml", ".yml"}:
        _render_discovery_from_config(input_path)
        return
    if input_path.suffix.lower() == ".json" and _looks_like_candidate_manifest(input_path):
        _render_discovery_from_manifest(input_path)
        return
    _render_preview_from_planes(input_path)


def _render_discovery_from_config(config_path: Path) -> None:
    config = load_config(config_path)
    if config.target is None:
        st.title("Galaxy Project")
        st.info("This project is pinned to explicit source products. Open a workdir or aligned planes export to edit preview state.")
        _render_project_save_controls(config, config_path, key_prefix="project")
        return

    query_key = _discovery_query_key(config)
    cache_key = f"discovery:{config_path.resolve()}:{query_key}"
    cache_path = _discovery_cache_status(_discovery_cache_path(config_path), query_key)
    refresh_requested = st.sidebar.button("Refresh discovery")
    allow_stale = False
    if cache_path == "stale":
        st.sidebar.warning("Saved discovery results are older than 6 months.")
        allow_stale = st.sidebar.button("Use stale cache")
    if refresh_requested:
        st.session_state.pop(cache_key, None)
    if cache_key not in st.session_state or refresh_requested:
        st.session_state[cache_key] = _load_or_query_discovery_manifest(
            config_path,
            config,
            query_key,
            force_refresh=refresh_requested,
            allow_stale=allow_stale,
        )
    manifest = st.session_state[cache_key]
    _render_discovery_controls(manifest, config, config.search, config_path)


def _render_discovery_from_manifest(manifest_path: Path) -> None:
    cache_key = f"manifest:{manifest_path.resolve()}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = load_candidate_manifest(manifest_path)
    manifest = st.session_state[cache_key]
    config_path = Path(manifest.config_path) if manifest.config_path else None
    base_config = load_config(config_path) if config_path is not None and config_path.exists() else None
    search = (
        base_config.search
        if base_config is not None
        else SearchConfig(
            observation_selection=manifest.selection_policy,
            max_observations_per_filter=manifest.max_observations_per_filter,
        )
    )
    _render_discovery_controls(manifest, base_config, search, config_path)


def _render_discovery_controls(
    manifest: CandidateManifest,
    base_config: GalaxyConfig | None,
    search: SearchConfig,
    config_path: Path | None,
) -> None:
    st.title("Archive Discovery")
    selection_inputs = _ui_selection_inputs(manifest)
    updated_candidates = apply_selection_policy(manifest.candidates, search, selection_inputs)
    updated_manifest = CandidateManifest(
        generated_at=manifest.generated_at,
        config_path=str(config_path) if config_path else manifest.config_path,
        selection_policy=selection_inputs.strategy or search.observation_selection,
        max_observations_per_filter=selection_inputs.max_per_filter or search.max_observations_per_filter,
        selection_inputs=selection_inputs,
        candidates=updated_candidates,
    )
    _render_bulk_actions(updated_manifest)
    updated_manifest = _render_candidate_editor(updated_manifest, search)
    _render_discovery_summary(updated_manifest)
    payload = json.dumps(updated_manifest.to_dict(), indent=2)
    st.download_button("Export selection manifest", payload, file_name="candidates.json")
    if config_path is not None and base_config is not None:
        project = _project_from_discovery_state(base_config, updated_manifest)
        _render_project_save_controls(project, config_path, key_prefix="discovery")
        workdir = st.text_input("Workdir", value=str(config_path.parent / "artifacts" / "streamlit-run"))
        if st.button("Run pipeline from current selection"):
            artifacts = run_pipeline(
                project,
                workdir,
                mode="full",
                selection_manifest=updated_manifest,
                config_path=str(config_path),
            )
            st.success(f"Artifacts written to {artifacts.workdir}")
    else:
        st.info("This manifest does not include a project path, so project save and pipeline execution are unavailable here.")


def _render_bulk_actions(manifest: CandidateManifest) -> None:
    col1, col2, col3 = st.columns(3)
    if col1.button("Select all visible"):
        for candidate in manifest.candidates:
            candidate.user_selected = True
    if col2.button("Clear selection"):
        for candidate in manifest.candidates:
            candidate.user_selected = False
    if col3.button("Reset explicit overrides"):
        for candidate in manifest.candidates:
            candidate.user_selected = None


def _render_candidate_editor(manifest: CandidateManifest, search: SearchConfig) -> CandidateManifest:
    rows = []
    for candidate in manifest.candidates:
        rows.append(
            {
                "include": candidate.selected,
                "candidate_id": candidate.candidate_id,
                "date": candidate.observation_date_end or candidate.observation_date_start,
                "mission": candidate.mission,
                "instrument": candidate.instrument,
                "detector": candidate.detector,
                "filter": candidate.filter_name,
                "product_type": candidate.product_type,
                "exposure_time": candidate.exposure_time,
                "file_size": candidate.file_size,
                "proposal_id": candidate.proposal_id,
                "product_filename": candidate.product_filename,
                "auto_selection": candidate.auto_selection_reason,
                "details": candidate.proposal_title or candidate.target_name or "",
            }
        )
    edited = st.data_editor(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    by_id = {candidate.candidate_id: candidate for candidate in manifest.candidates}
    for row in edited.to_dict("records"):
        candidate = by_id[row["candidate_id"]]
        candidate.user_selected = bool(row["include"])
    refreshed = apply_selection_policy(manifest.candidates, search, manifest.selection_inputs)
    return CandidateManifest(
        generated_at=manifest.generated_at,
        config_path=manifest.config_path,
        selection_policy=manifest.selection_policy,
        max_observations_per_filter=manifest.max_observations_per_filter,
        selection_inputs=manifest.selection_inputs,
        candidates=refreshed,
    )


def _render_discovery_summary(manifest: CandidateManifest) -> None:
    selected = [candidate for candidate in manifest.candidates if candidate.selected]
    total_size = sum(candidate.file_size or 0 for candidate in selected)
    st.subheader("Selection Summary")
    st.write(f"Candidates: {len(manifest.candidates)}")
    st.write(f"Selected: {len(selected)}")
    st.write(f"Estimated download volume: {total_size / (1024 * 1024):.2f} MiB")


def _ui_selection_inputs(manifest: CandidateManifest) -> SelectionInputs:
    st.sidebar.header("Selection")
    strategy_label = st.sidebar.radio(
        "Policy",
        options=["all", "latest_per_filter", "deepest_per_filter"],
        index=["all", "latest_per_filter", "deepest_per_filter"].index(manifest.selection_policy),
    )
    max_per_filter = st.sidebar.number_input(
        "Max observations per filter",
        min_value=1,
        value=int(manifest.max_observations_per_filter),
        step=1,
    )
    max_total = st.sidebar.number_input(
        "Max total",
        min_value=0,
        value=int(manifest.selection_inputs.max_total or 0),
        step=1,
    )
    filters = sorted({candidate.filter_name for candidate in manifest.candidates if candidate.filter_name})
    instruments = sorted({candidate.instrument for candidate in manifest.candidates if candidate.instrument})
    missions = sorted({candidate.mission for candidate in manifest.candidates if candidate.mission})
    include_filters = st.sidebar.multiselect("Include filters", filters, default=sorted(manifest.selection_inputs.include_filters))
    include_instruments = st.sidebar.multiselect("Include instruments", instruments, default=sorted(manifest.selection_inputs.include_instruments))
    include_missions = st.sidebar.multiselect("Include missions", missions, default=sorted(manifest.selection_inputs.include_missions))
    return SelectionInputs(
        include_filters={str(item).upper() for item in include_filters},
        include_instruments={str(item).upper() for item in include_instruments},
        include_missions={str(item).upper() for item in include_missions},
        include_obsids=set(manifest.selection_inputs.include_obsids),
        exclude_obsids=set(manifest.selection_inputs.exclude_obsids),
        include_products=set(manifest.selection_inputs.include_products),
        exclude_products=set(manifest.selection_inputs.exclude_products),
        strategy=strategy_label,
        max_per_filter=int(max_per_filter),
        max_total=int(max_total) if int(max_total) > 0 else None,
    )


def _render_preview_from_planes(planes_path: Path) -> None:
    st.title("Preview")
    preview_branches = _preview_branch_paths(planes_path)
    selected_branch = _preview_branch_selector(preview_branches, planes_path)
    active_planes_path = preview_branches[selected_branch] if preview_branches else planes_path
    plane_records = load_multiplane_records(active_planes_path)
    planes = {record.plane_id: record.data for record in plane_records}
    metadata = {record.plane_id: record.metadata for record in plane_records}
    config_path = _associated_project_path(active_planes_path)
    base_config = load_config(config_path) if config_path is not None and config_path.exists() else None

    st.caption(f"Branch: {selected_branch} ({active_planes_path.name})")
    st.sidebar.header("Planes")
    _seed_preview_from_project(base_config, list(planes.keys()), metadata)
    _style_loader(list(planes.keys()))
    enabled = {name for name in planes if st.sidebar.checkbox(name, key=_enabled_key(name))}

    mapping = _mapping_controls(list(planes.keys()), metadata)
    tone = _tone_controls()

    composed = compose_channels(CompositionInputs(planes=planes, metadata=metadata), mapping, enabled)
    rgb = apply_tone(composed, tone, bit_depth=16).astype(np.uint16)
    preview = np.clip(rgb / 257.0, 0, 255).astype(np.uint8)

    st.image(preview, caption="Preview", use_container_width=True)

    state = {
        "mapping": mapping.model_dump(mode="json"),
        "tone": tone.model_dump(mode="json"),
        "enabled_planes": sorted(enabled),
    }
    st.sidebar.download_button("Download style YAML", yaml.safe_dump(state, sort_keys=False), file_name="galaxy-style.yaml")
    st.sidebar.download_button("Download style JSON", json.dumps(state, indent=2), file_name="galaxy-style.json")
    if base_config is not None and config_path is not None:
        project = _project_from_preview_state(base_config, enabled, mapping, tone, metadata)
        _render_project_save_controls(project, config_path, key_prefix="preview")


def _resolve_input_path() -> Path | None:
    env_path = os.environ.get("GALAXY_UI_INPUT_PATH")
    if env_path:
        resolved = _resolve_input_candidate(Path(env_path))
        if resolved is not None:
            return resolved

    args = sys.argv[1:]
    for arg in args:
        resolved = _resolve_input_candidate(Path(arg))
        if resolved is not None:
            return resolved

    return _discover_default_input(Path.cwd())


def _resolve_input_candidate(candidate: Path) -> Path | None:
    if candidate.is_dir():
        preview_branches = _preview_branch_paths(candidate)
        if preview_branches:
            return preview_branches["original"] if "original" in preview_branches else next(iter(preview_branches.values()))
        nested_manifest = candidate / "candidates.json"
        if nested_manifest.exists():
            return nested_manifest
        return _find_project_in_directory(candidate)
    if not candidate.exists():
        return None
    if candidate.suffix.lower() in {".yaml", ".yml"} and candidate.name in PROJECT_FILE_NAMES:
        return candidate
    return candidate


def _discover_default_input(root: Path) -> Path | None:
    artifacts_dir = root / "artifacts"
    if artifacts_dir.exists():
        for pattern in ("**/exported_planes.fits", "**/exported_planes_deconvolved.fits", "**/candidates.json", "**/project.yaml"):
            matches = sorted(artifacts_dir.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
            for match in matches:
                resolved = _resolve_input_candidate(match)
                if resolved is not None:
                    return resolved

    examples_dir = root / "examples"
    if examples_dir.exists():
        yaml_matches = sorted(
            [*examples_dir.glob("*.yaml"), *examples_dir.glob("*.yml")],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if len(yaml_matches) == 1:
            return yaml_matches[0]
    return None


def _discovery_query_key(config) -> str:
    payload = {
        "target": config.target.model_dump(mode="json") if config.target is not None else None,
        "search": {
            "missions": config.search.missions,
            "instruments": config.search.instruments,
            "detectors": config.search.detectors,
            "filters": config.search.filters,
            "product_types": config.search.product_types,
            "observation_date_start": config.search.observation_date_start,
            "observation_date_end": config.search.observation_date_end,
            "source_products": [item.model_dump(mode="json") for item in config.search.source_products],
        },
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _discovery_cache_path(config_path: Path) -> Path:
    if config_path.name in PROJECT_FILE_NAMES:
        return config_path.parent / "candidates.json"
    if config_path.parent.name == "examples":
        return config_path.parent.parent / "artifacts" / config_path.stem / "candidates.json"
    return config_path.parent / "artifacts" / config_path.stem / "candidates.json"


def _load_or_query_discovery_manifest(
    config_path: Path,
    config,
    query_key: str,
    *,
    force_refresh: bool = False,
    allow_stale: bool = False,
    now: datetime | None = None,
) -> CandidateManifest:
    cache_path = _discovery_cache_path(config_path)
    if not force_refresh and cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("discovery_cache_key") == query_key:
                cache_generated_at = _manifest_generated_at(payload)
                if cache_generated_at is not None and not _discovery_cache_is_stale(cache_generated_at, now=now):
                    return CandidateManifest.from_dict(payload)
                if allow_stale:
                    return CandidateManifest.from_dict(payload)
        except json.JSONDecodeError:
            pass

    if config.target is None:
        raise RuntimeError("discovery cache refresh requires a target-defined search project")
    resolved_target = resolve_target(config.target)
    shape_kind, shape_kwargs = region_to_mast_shape(config.target.region, resolved_target.coord)
    candidates = discover_candidates(shape_kind, shape_kwargs, config.search)
    manifest = build_candidate_manifest(candidates, config.search, config_path=str(config_path))
    payload = manifest.to_dict()
    payload["discovery_cache_key"] = query_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest


def _discovery_cache_status(cache_path: Path, query_key: str, now: datetime | None = None) -> str:
    if not cache_path.exists():
        return "missing"
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "invalid"
    if payload.get("discovery_cache_key") != query_key:
        return "mismatch"
    generated_at = _manifest_generated_at(payload)
    if generated_at is None:
        return "stale"
    return "stale" if _discovery_cache_is_stale(generated_at, now=now) else "fresh"


def _manifest_generated_at(payload: dict[str, Any]) -> datetime | None:
    raw = payload.get("generated_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _discovery_cache_is_stale(generated_at: datetime, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return current - generated_at > DISCOVERY_CACHE_MAX_AGE


def _looks_like_candidate_manifest(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("candidates"), list)


def _preview_branch_paths(candidate: Path) -> dict[str, Path]:
    if candidate.is_dir():
        directory = candidate
    elif candidate.name in PREVIEW_BRANCH_FILE_NAMES.values():
        directory = candidate.parent
    elif candidate.name in PROJECT_FILE_NAMES:
        directory = candidate.parent
    else:
        return {}

    branches = {
        branch: directory / filename
        for branch, filename in PREVIEW_BRANCH_FILE_NAMES.items()
        if (directory / filename).exists()
    }
    return branches


def _preview_branch_selector(preview_branches: dict[str, Path], active_path: Path) -> str:
    if not preview_branches:
        return "original"
    if len(preview_branches) == 1:
        return next(iter(preview_branches))

    default_branch = _branch_name_for_path(active_path)
    options = [branch for branch in ("original", "deconvolved") if branch in preview_branches]
    default_index = options.index(default_branch) if default_branch in options else 0
    return st.sidebar.selectbox("Preview branch", options=options, index=default_index)


def _branch_name_for_path(path: Path) -> str:
    for branch, filename in PREVIEW_BRANCH_FILE_NAMES.items():
        if path.name == filename:
            return branch
    return "original"


def _mapping_controls(plane_names: list[str], metadata: dict[str, dict[str, object]]) -> MappingConfig:
    mappings: list[PlaneMappingConfig] = []
    defaults = {item.plane: item.rgb for item in default_plane_mappings(metadata)}
    st.sidebar.header("Plane RGB Mix")
    for plane_name in plane_names:
        filter_name = str(metadata.get(plane_name, {}).get("filter") or "")
        title = plane_name if not filter_name or filter_name == plane_name else f"{plane_name} ({filter_name})"
        st.sidebar.subheader(title)
        default_rgb = defaults.get(plane_name, RGBMixConfig())
        weights: dict[str, float] = {}
        for channel in ("red", "green", "blue"):
            weight_key = _weight_key(channel, plane_name)
            if weight_key not in st.session_state:
                st.session_state[weight_key] = float(getattr(default_rgb, channel))
            weights[channel] = float(
                st.sidebar.slider(
                    f"{channel}:{plane_name}",
                    min_value=0.0,
                    max_value=3.0,
                    step=0.05,
                    key=weight_key,
                )
            )
        if any(weights.values()):
            mappings.append(
                PlaneMappingConfig(
                    plane=plane_name,
                    filter=filter_name or None,
                    label=filter_name or plane_name,
                    rgb=RGBMixConfig(**weights),
                )
            )
    return MappingConfig(defaults=MappingDefaults(strategy="continuum"), planes=mappings, derived_planes=[])


def _tone_controls() -> ToneConfig:
    st.sidebar.header("Tone")
    _ensure_default("tone:black", 1.0)
    _ensure_default("tone:white", 99.5)
    _ensure_default("tone:saturation", 1.0)
    black = st.sidebar.slider("Black percentile", 0.0, 20.0, 0.0, 0.1, key="tone:black")
    white = st.sidebar.slider("White percentile", 80.0, 100.0, 100.0, 0.1, key="tone:white")
    saturation = st.sidebar.slider("Saturation", 0.0, 3.0, 0.0, 0.05, key="tone:saturation")
    gains = {}
    stretch = {}
    for channel in ("red", "green", "blue"):
        gain_key = f"tone:gain:{channel}"
        stretch_kind_key = f"tone:stretch-kind:{channel}"
        stretch_param_key = f"tone:stretch-parameter:{channel}"
        _ensure_default(gain_key, 1.0)
        _ensure_default(stretch_kind_key, "asinh")
        _ensure_default(stretch_param_key, 4.0)
        gains[channel] = st.sidebar.slider(f"{channel.title()} gain", 0.0, 3.0, 0.0, 0.05, key=gain_key)
        kind = st.sidebar.selectbox(
            f"{channel.title()} stretch",
            ("asinh", "gamma"),
            index=0 if st.session_state[stretch_kind_key] == "asinh" else 1,
            key=stretch_kind_key,
        )
        parameter = st.sidebar.slider(
            f"{channel.title()} stretch parameter",
            0.1,
            10.0,
            0.1,
            0.1,
            key=stretch_param_key,
        )
        stretch[channel] = StretchConfig(kind=kind, parameter=parameter)
    return ToneConfig(
        stretch=ToneStretchSet(**stretch),
        percentiles=TonePercentiles(black=black, white=white),
        gain=ToneGainBias(**gains),
        bias=ToneGainBias(red=0.0, green=0.0, blue=0.0),
        saturation=saturation,
    )


def _style_loader(plane_names: list[str]) -> None:
    uploaded = st.sidebar.file_uploader("Load style YAML/JSON", type=["yaml", "yml", "json"])
    if not uploaded:
        for plane_name in plane_names:
            _ensure_default(_enabled_key(plane_name), True)
        return

    style_text = uploaded.getvalue().decode("utf-8")
    fingerprint = f"{uploaded.name}:{hash(style_text)}"
    if st.session_state.get("style:fingerprint") == fingerprint:
        return

    style = _parse_style_document(style_text)
    _seed_style_state(style, plane_names)
    st.session_state["style:fingerprint"] = fingerprint


def _parse_style_document(text: str) -> dict[str, Any]:
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError("style document must contain a mapping at the top level")
    return parsed


def _seed_style_state(style: dict[str, Any], plane_names: list[str]) -> None:
    enabled = {str(name) for name in style.get("enabled_planes", [])}
    mapping = style.get("mapping", {})
    tone = style.get("tone", {})
    stretch = tone.get("stretch", {})
    gain = tone.get("gain", {})
    percentiles = tone.get("percentiles", {})
    plane_weights = _style_plane_weights(mapping)

    for plane_name in plane_names:
        st.session_state[_enabled_key(plane_name)] = plane_name in enabled if enabled else True

    for plane_name in plane_names:
        weights = plane_weights.get(plane_name, {"red": 0.0, "green": 0.0, "blue": 0.0})
        for channel in ("red", "green", "blue"):
            st.session_state[_weight_key(channel, plane_name)] = float(weights.get(channel, 0.0))

    for channel in ("red", "green", "blue"):
        st.session_state[f"tone:gain:{channel}"] = float(gain.get(channel, 1.0))
        stretch_cfg = stretch.get(channel, {})
        st.session_state[f"tone:stretch-kind:{channel}"] = str(stretch_cfg.get("kind", "asinh"))
        st.session_state[f"tone:stretch-parameter:{channel}"] = float(stretch_cfg.get("parameter", 4.0))

    st.session_state["tone:black"] = float(percentiles.get("black", 1.0))
    st.session_state["tone:white"] = float(percentiles.get("white", 99.5))
    st.session_state["tone:saturation"] = float(tone.get("saturation", 1.0))


def _style_plane_weights(mapping: dict[str, Any]) -> dict[str, dict[str, float]]:
    plane_weights: dict[str, dict[str, float]] = {}
    for item in mapping.get("planes", []):
        if not isinstance(item, dict):
            continue
        plane_name = item.get("plane")
        rgb = item.get("rgb", {})
        if not plane_name or not isinstance(rgb, dict):
            continue
        plane_weights[str(plane_name)] = {
            "red": float(rgb.get("red", 0.0)),
            "green": float(rgb.get("green", 0.0)),
            "blue": float(rgb.get("blue", 0.0)),
        }
    return plane_weights


def _seed_preview_from_project(
    base_config: GalaxyConfig | None,
    plane_names: list[str],
    metadata: dict[str, dict[str, object]],
) -> None:
    if base_config is None:
        return
    fingerprint = f"project:{hash(base_config.to_yaml())}:{','.join(sorted(plane_names))}"
    if st.session_state.get("project:fingerprint") == fingerprint:
        return

    mapping_by_plane: dict[str, RGBMixConfig] = {}
    mapping_by_filter: dict[str, RGBMixConfig] = {}
    for item in base_config.mapping.planes:
        if item.plane:
            mapping_by_plane[item.plane] = item.rgb
        if item.filter:
            mapping_by_filter[str(item.filter).upper()] = item.rgb

    disabled_plane_ids = set(base_config.planes.disabled_plane_ids)
    enabled_filters = {item.upper() for item in base_config.planes.enabled_filters}
    for plane_name in plane_names:
        filter_name = str(metadata.get(plane_name, {}).get("filter") or "").upper()
        enabled = plane_name not in disabled_plane_ids and (not enabled_filters or filter_name in enabled_filters)
        st.session_state[_enabled_key(plane_name)] = enabled
        rgb = mapping_by_plane.get(plane_name) or mapping_by_filter.get(filter_name)
        if rgb is not None:
            for channel in ("red", "green", "blue"):
                st.session_state[_weight_key(channel, plane_name)] = float(getattr(rgb, channel))

    for channel in ("red", "green", "blue"):
        st.session_state[f"tone:gain:{channel}"] = float(getattr(base_config.tone.gain, channel))
        st.session_state[f"tone:stretch-kind:{channel}"] = str(getattr(base_config.tone.stretch, channel).kind)
        st.session_state[f"tone:stretch-parameter:{channel}"] = float(getattr(base_config.tone.stretch, channel).parameter)

    st.session_state["tone:black"] = float(base_config.tone.percentiles.black)
    st.session_state["tone:white"] = float(base_config.tone.percentiles.white)
    st.session_state["tone:saturation"] = float(base_config.tone.saturation)
    st.session_state["project:fingerprint"] = fingerprint


def _project_from_discovery_state(base_config: GalaxyConfig, manifest: CandidateManifest) -> GalaxyConfig:
    search = base_config.search.model_copy(
        update={
            "observation_selection": manifest.selection_policy,
            "max_observations_per_filter": manifest.max_observations_per_filter,
            "max_total_observations": manifest.selection_inputs.max_total,
            "filters": sorted(manifest.selection_inputs.include_filters) if manifest.selection_inputs.include_filters else base_config.search.filters,
            "instruments": sorted(manifest.selection_inputs.include_instruments) if manifest.selection_inputs.include_instruments else base_config.search.instruments,
            "missions": sorted(manifest.selection_inputs.include_missions) if manifest.selection_inputs.include_missions else base_config.search.missions,
        }
    )
    return base_config.model_copy(update={"search": search})


def _project_from_preview_state(
    base_config: GalaxyConfig,
    enabled_planes: set[str],
    mapping: MappingConfig,
    tone: ToneConfig,
    metadata: dict[str, dict[str, object]],
) -> GalaxyConfig:
    all_plane_ids = sorted(str(name) for name in metadata)
    enabled_filters = sorted(
        {
            str(metadata[name].get("filter") or "").upper()
            for name in enabled_planes
            if str(metadata[name].get("filter") or "")
        }
    )
    planes = base_config.planes.model_copy(
        update={
            "enabled_filters": enabled_filters,
            "disabled_plane_ids": sorted(set(all_plane_ids) - {str(name) for name in enabled_planes}),
        }
    )
    return base_config.model_copy(update={"planes": planes, "mapping": mapping, "tone": tone})


def _render_project_save_controls(project: GalaxyConfig, config_path: Path, *, key_prefix: str) -> None:
    st.sidebar.header("Project")
    default_path = _default_project_save_path(config_path)
    save_path_text = st.sidebar.text_input("Project save path", value=str(default_path), key=f"{key_prefix}:project-save-path")
    project_yaml = project.to_yaml()
    st.sidebar.download_button(
        "Download Galaxy project",
        project_yaml,
        file_name=Path(save_path_text).name,
        key=f"{key_prefix}:download-project",
    )
    if st.sidebar.button("Save Galaxy project", key=f"{key_prefix}:save-project"):
        destination = Path(save_path_text)
        destination.parent.mkdir(parents=True, exist_ok=True)
        dump_config(project, destination)
        st.sidebar.success(f"Saved project to {destination}")


def _default_project_save_path(config_path: Path) -> Path:
    if config_path.name in PROJECT_FILE_NAMES:
        return config_path.parent / "project.yaml"
    if config_path.parent.name == "examples":
        return config_path.parent.parent / "artifacts" / config_path.stem / "project.yaml"
    return config_path.parent / f"{config_path.stem}.project.yaml"


def _find_project_in_directory(directory: Path) -> Path | None:
    for name in PROJECT_FILE_NAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _associated_project_path(candidate: Path) -> Path | None:
    if candidate.is_dir():
        return _find_project_in_directory(candidate)
    if candidate.name in PREVIEW_BRANCH_FILE_NAMES.values():
        return _find_project_in_directory(candidate.parent)
    if candidate.name in PROJECT_FILE_NAMES:
        return candidate
    return None


def _enabled_key(plane_name: str) -> str:
    return f"plane:enabled:{plane_name}"


def _weight_key(channel: str, plane_name: str) -> str:
    return f"mapping:{channel}:{plane_name}"


def _ensure_default(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


if __name__ == "__main__":  # pragma: no cover
    main()






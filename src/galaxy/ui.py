"""Streamlit UI for the five-screen JSON scene-card workflow."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from galaxy.app_config import ApplicationConfigError, ApplicationSettings, load_application_settings, parse_ui_startup_args
from galaxy.discovery_sources import (
    DiscoverySourceQuery, YuvalHarpazLatestReleaseSource, discover_isolated,
)
from galaxy.discovery_cache import load_cached_candidates, save_cached_candidates
from galaxy.mapping import CompositionInputs, compose_channels, default_plane_mappings
from galaxy.mast import ArchiveQueryStatus, apply_selection_policy, build_candidate_manifest, query_archive_outcome
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import (
    MappingConfig, SearchConfig, StretchConfig, ToneConfig, ToneGainBias,
    TonePercentiles, ToneStretchSet,
)
from galaxy.scene_card import asset_path, create_scene, document, edit_scene, load_scene
from galaxy.scene_models import SceneCard
from galaxy.render_jobs import RenderJob, request_cancellation_before_departure, start_render_job
from galaxy.scene_workflow import (
    LibraryEntry, LibraryOrigin, OperationPhase, Screen, apply_manifest_selection, default_scene_path,
    discover_workspace_inputs, draft_from_discovery_hint, draft_from_resolver_match,
    draft_from_target, duplicate_library_scene,
    export_current_render, initialize_canvas, inspect_scene_artifacts, list_project_library, matching_render,
    manifest_from_card, materialize_render_defaults, render_issues, resolve_workdir_input, resize_canvas,
    merge_render_completion, save_draft, save_example_as_user_scene,
)
from galaxy.selection import CandidateManifest, CandidateRecord, load_candidate_manifest
from galaxy.targeting import ResolverOutcome, ResolverStatus, region_to_mast_shape, resolve_name, resolve_target
from galaxy.tone import apply_tone


SCREENS = [screen.value for screen in Screen]


def main() -> None:
    _startup_message("starting")
    st.set_page_config(page_title="Galaxy", layout="wide")
    try:
        scene_dir, input_args = parse_ui_startup_args(sys.argv[1:])
        settings = load_application_settings(scene_dir)
    except (ApplicationConfigError, SystemExit) as exc:
        st.error(str(exc))
        return
    _startup_message(f"configuration loaded; scene directory={settings.scene_directory}")
    st.session_state["application_settings"] = settings
    try:
        _startup_message("initializing session")
        _initialize_session(settings, _explicit_input(input_args))
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    _startup_message(f"rendering screen={st.session_state.get('screen', '<unset>')}")
    _render_app(settings)


def _startup_message(message: str) -> None:
    print(f"[galaxy-ui] {message}", flush=True)


def _widget_changed(key: str) -> None:
    _startup_message(f"widget changed; {key}={st.session_state.get(key)!r}")


def _workflow_changed() -> None:
    st.session_state["screen"] = st.session_state["workflow-screen"]
    _widget_changed("workflow-screen")


def _initialize_session(settings: ApplicationSettings, explicit: Path | None) -> None:
    state = st.session_state
    _startup_message("setting session defaults")
    state.setdefault("screen", Screen.DISCOVERY.value)
    state.setdefault("active_card", None)
    state.setdefault("active_path", None)
    state.setdefault("active_origin", LibraryOrigin.USER_SCENE.value)
    state.setdefault("saved_document", None)
    state.setdefault("candidate_manifest", None)
    state.setdefault("planes_path", None)
    state.setdefault("operation_phase", OperationPhase.IDLE.value)
    state.setdefault("operation_message", "")
    state.setdefault("resolver_outcome", None)
    state.setdefault("discovery_hints", ())
    state.setdefault("discovery_failures", ())
    state.setdefault("render_job", None)
    if "workspace_inputs" not in state:
        _startup_message(f"scanning workspace inputs under {settings.project_root}")
        state["workspace_inputs"] = discover_workspace_inputs(settings.project_root)
    _startup_message(f"workspace inputs ready; count={len(state['workspace_inputs'])}")
    if explicit is None or state.get("routed_input") == str(explicit.resolve()):
        _startup_message("no explicit startup input")
        return
    _startup_message(f"routing explicit startup input={explicit}")
    route = resolve_workdir_input(explicit)
    if route.kind == "scene":
        origin = (
            LibraryOrigin.BUNDLED_EXAMPLE
            if route.path.parent == (settings.project_root / "artifacts").resolve()
            else LibraryOrigin.USER_SCENE
        )
        _set_active_scene(load_scene(route.path), route.path, saved=True, origin=origin)
    elif route.kind == "manifest":
        manifest = load_candidate_manifest(route.path)
        st.session_state["candidate_manifest"] = manifest
        card = _card_for_manifest(manifest)
        _set_active_scene(card, None, saved=False)
    else:
        state["planes_path"] = route.path
        state["screen"] = Screen.RENDER.value
    state["routed_input"] = str(explicit.resolve())


def _explicit_input(args: list[str]) -> Path | None:
    environment = os.environ.get("GALAXY_UI_INPUT_PATH")
    if environment:
        return Path(environment)
    return Path(args[0]) if args else None


def _card_for_manifest(manifest: CandidateManifest) -> SceneCard:
    if manifest.config_path:
        candidate = Path(manifest.config_path)
        if candidate.is_file() and candidate.suffix.lower() == ".json":
            try:
                return load_scene(candidate)
            except (OSError, ValueError):
                pass
    return create_scene("Imported candidate selection")


def _set_active_scene(
    card: SceneCard, path: Path | None, *, saved: bool,
    origin: LibraryOrigin = LibraryOrigin.USER_SCENE,
) -> None:
    st.session_state["active_card"] = card
    st.session_state["active_path"] = path
    st.session_state["saved_document"] = document(card) if saved else None
    st.session_state["active_origin"] = origin.value
    st.session_state["planes_path"] = None
    st.session_state["screen"] = Screen.REFINEMENT.value
    for key in ("candidate-editor", "render-branch", "output-overwrite"):
        st.session_state.pop(key, None)


def _request_scene_replacement(
    card: SceneCard, path: Path | None, *, saved: bool,
    origin: LibraryOrigin = LibraryOrigin.USER_SCENE,
) -> bool:
    """Install immediately or retain a pending replacement until dirty-scene choice."""
    if request_cancellation_before_departure(st.session_state.get("render_job")):
        st.session_state["pending_scene"] = (card, path, saved, origin)
        st.session_state["operation_message"] = (
            "Cancellation requested before replacing the active scene"
        )
        return False
    if _is_dirty():
        st.session_state["pending_scene"] = (card, path, saved, origin)
        return False
    _set_active_scene(card, path, saved=saved, origin=origin)
    return True


def _is_dirty() -> bool:
    card = st.session_state.get("active_card")
    if card is None:
        return False
    return document(card) != st.session_state.get("saved_document")


def _render_app(settings: ApplicationSettings) -> None:
    st.sidebar.title("Galaxy")
    if st.session_state.get("workflow-screen") != st.session_state["screen"]:
        st.session_state["workflow-screen"] = st.session_state["screen"]
    selected = st.sidebar.radio(
        "Workflow", SCREENS, key="workflow-screen", on_change=_workflow_changed
    )
    card = st.session_state.get("active_card")
    if card is not None:
        marker = "Unsaved changes" if _is_dirty() else "Saved"
        if st.session_state.get("active_origin") == LibraryOrigin.BUNDLED_EXAMPLE.value:
            marker = f"Bundled example - {marker}"
        st.sidebar.caption(f"{card.title} - {marker}")
        if st.sidebar.button("Close active scene"):
            st.session_state["pending_close"] = True
            st.rerun()
    phase = st.session_state.get("operation_phase", OperationPhase.IDLE.value)
    message = st.session_state.get("operation_message", "")
    st.sidebar.caption(f"Operation: {phase}" + (f" - {message}" if message else ""))
    if st.session_state.get("pending_scene") is not None:
        _render_unsaved_replacement(settings)
        return
    if st.session_state.get("pending_close"):
        _render_unsaved_close(settings)
        return
    renderers = {
        Screen.DISCOVERY.value: _render_discovery,
        Screen.REFINEMENT.value: _render_refinement,
        Screen.RENDER.value: _render_render,
        Screen.OUTPUT.value: _render_output,
        Screen.LIBRARY.value: _render_library,
    }
    renderers[selected](settings)


def _render_unsaved_replacement(settings: ApplicationSettings) -> None:
    if _render_departure_wait("replacing the active scene", "pending_scene"):
        return
    if not _is_dirty():
        card, path, saved, origin = st.session_state.pop("pending_scene")
        _set_active_scene(card, path, saved=saved, origin=origin)
        st.rerun()
    st.warning("The active scene has unsaved changes.")
    st.write("Save, discard, or cancel before replacing it.")
    save_column, discard_column, cancel_column = st.columns(3)
    if save_column.button("Save and continue"):
        if _save_active(settings):
            card, path, saved, origin = st.session_state.pop("pending_scene")
            _set_active_scene(card, path, saved=saved, origin=origin)
            st.rerun()
    if discard_column.button("Discard and continue"):
        card, path, saved, origin = st.session_state.pop("pending_scene")
        _set_active_scene(card, path, saved=saved, origin=origin)
        st.rerun()
    if cancel_column.button("Cancel"):
        st.session_state.pop("pending_scene")
        st.rerun()


def _render_unsaved_close(settings: ApplicationSettings) -> None:
    if _render_departure_wait("closing the active scene", "pending_close"):
        return
    if not _is_dirty():
        _close_active_scene()
        st.rerun()
    st.warning("The active scene has unsaved changes.")
    st.write("Save, discard, or cancel before closing it.")
    save_column, discard_column, cancel_column = st.columns(3)
    if save_column.button("Save and close") and _save_active(settings):
        _close_active_scene()
        st.rerun()
    if discard_column.button("Discard and close"):
        _close_active_scene()
        st.rerun()
    if cancel_column.button("Cancel close"):
        st.session_state.pop("pending_close", None)
        st.rerun()


def _close_active_scene() -> None:
    request_cancellation_before_departure(st.session_state.get("render_job"))
    for key in (
        "active_card", "active_path", "active_origin", "saved_document", "candidate_manifest", "planes_path",
        "pending_close", "render_job", "render_job_applied", "candidate-editor",
        "render-branch", "output-overwrite",
    ):
        st.session_state.pop(key, None)
    st.session_state["screen"] = Screen.DISCOVERY.value


def _render_departure_wait(action: str, pending_key: str) -> bool:
    job: RenderJob | None = st.session_state.get("render_job")
    if job is None:
        return False
    if not request_cancellation_before_departure(job):
        st.session_state["render_job"] = None
        st.session_state["render_job_applied"] = False
        return False
    st.warning(f"Render cancellation was requested before {action}.")
    st.write("Departure will continue after the worker reaches a safe stage boundary.")
    refresh, keep = st.columns(2)
    if refresh.button("Refresh cancellation status"):
        st.rerun()
    if keep.button("Keep current scene"):
        st.session_state.pop(pending_key, None)
        st.rerun()
    return True


def _save_active(settings: ApplicationSettings) -> bool:
    card = st.session_state.get("active_card")
    if card is None:
        st.error("No active scene.")
        return False
    try:
        if st.session_state.get("active_origin") == LibraryOrigin.BUNDLED_EXAMPLE.value:
            committed, path = save_example_as_user_scene(card, settings.scene_directory)
        else:
            committed, path = save_draft(
                card, settings.scene_directory, st.session_state.get("active_path")
            )
    except (OSError, ValueError) as exc:
        st.session_state["operation_phase"] = OperationPhase.FAILED.value
        st.error(f"Scene save failed: {exc}")
        return False
    st.session_state["active_card"] = committed
    st.session_state["active_path"] = path
    st.session_state["active_origin"] = LibraryOrigin.USER_SCENE.value
    st.session_state["saved_document"] = document(committed)
    st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
    st.success(f"Scene saved to {path}")
    return True


def _save_label(default: str) -> str:
    return (
        "Save as new scene"
        if st.session_state.get("active_origin") == LibraryOrigin.BUNDLED_EXAMPLE.value
        else default
    )


def _render_discovery(settings: ApplicationSettings) -> None:
    st.title("Discovery")
    st.caption("Find a target by common name, coordinates, recent artifacts, or Saved scenes.")
    if st.button("Open Saved scenes"):
        st.session_state["screen"] = Screen.LIBRARY.value
        st.rerun()
    tab_name, tab_coordinates, tab_tracker, tab_existing = st.tabs(
        ["Name", "Coordinates", "Latest JWST releases", "Existing artifacts"]
    )
    with tab_name:
        name = st.text_input("Common name or catalog identifier", key="discovery_name")
        region_size = st.number_input("Search box size (arcmin)", min_value=0.01, value=2.0)
        if st.button("Resolve and refine", disabled=not name.strip()):
            st.session_state["operation_phase"] = OperationPhase.RUNNING.value
            outcome = resolve_name(name)
            st.session_state["resolver_outcome"] = outcome
            if outcome.status is ResolverStatus.RESOLVED:
                card = draft_from_resolver_match(name, outcome.matches[0], outcome.source,
                                                 region_size_arcmin=region_size)
                _request_scene_replacement(card, None, saved=False)
                st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
                st.session_state["operation_message"] = f"Resolved as {outcome.matches[0].label}"
                st.rerun()
            elif outcome.status is ResolverStatus.AMBIGUOUS:
                st.session_state["operation_phase"] = OperationPhase.IDLE.value
                st.session_state["operation_message"] = "Select one resolved target"
                st.rerun()
            else:
                st.session_state["operation_phase"] = OperationPhase.FAILED.value
                st.session_state["operation_message"] = outcome.message or outcome.status.value
        outcome: ResolverOutcome | None = st.session_state.get("resolver_outcome")
        if outcome and outcome.status is ResolverStatus.AMBIGUOUS:
            labels = [item.label for item in outcome.matches]
            chosen = st.selectbox("Choose the intended target", labels)
            if st.button("Use selected target"):
                match = outcome.matches[labels.index(chosen)]
                card = draft_from_resolver_match(name, match, outcome.source,
                                                 region_size_arcmin=region_size)
                _request_scene_replacement(card, None, saved=False)
                st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
                st.session_state["operation_message"] = f"Resolved as {match.label}"
                st.rerun()
        elif outcome and outcome.status in {ResolverStatus.UNRESOLVED, ResolverStatus.FAILED}:
            st.error(f"Name resolution {outcome.status.value}: {outcome.message or 'no match'}")
        st.info("A resolved name identifies a sky position; MAST coverage is checked in refinement.")
    with tab_coordinates:
        left, right = st.columns(2)
        ra = left.number_input("RA (degrees)", min_value=0.0, max_value=359.999999, value=0.0)
        dec = right.number_input("Dec (degrees)", min_value=-90.0, max_value=90.0, value=0.0)
        kind = st.radio(
            "Region", ["box", "circle"], horizontal=True,
            key="discovery-region", on_change=_widget_changed, args=("discovery-region",),
        )
        if kind == "box":
            width = st.number_input("Width (arcmin)", min_value=0.01, value=2.0)
            height = st.number_input("Height (arcmin)", min_value=0.01, value=2.0)
            arguments = {"width_arcmin": width, "height_arcmin": height}
        else:
            radius = st.number_input("Radius (arcmin)", min_value=0.01, value=1.0)
            arguments = {"radius_arcmin": radius}
        if st.button("Use sky region"):
            try:
                card = draft_from_target(ra_deg=ra, dec_deg=dec, region_kind=kind, **arguments)
                _request_scene_replacement(card, None, saved=False)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with tab_tracker:
        tracker_query = st.text_input("Filter tracker target, title, or proposal", key="tracker_query")
        maximum = int(st.number_input("Maximum tracker cards", min_value=1, max_value=100, value=24))
        st.number_input("Gallery position", min_value=0, value=0, key="discovery_gallery_scroll")
        if st.button("Load latest-release tracker"):
            st.session_state["operation_phase"] = OperationPhase.RUNNING.value
            batch = discover_isolated(
                [YuvalHarpazLatestReleaseSource()],
                DiscoverySourceQuery(text=tracker_query or None, max_results=maximum),
            )
            st.session_state["discovery_hints"] = batch.hints
            st.session_state["discovery_failures"] = batch.failures
            if batch.failures:
                st.session_state["operation_phase"] = OperationPhase.FAILED.value
                st.session_state["operation_message"] = batch.failures[0].message
            else:
                st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
                st.session_state["operation_message"] = f"Loaded {len(batch.hints)} tracker cards"
            st.rerun()
        for failure in st.session_state.get("discovery_failures", ()):
            st.warning(f"{failure.source_name} unavailable: {failure.message}. Name, coordinate, and MAST discovery remain available.")
        for index, hint in enumerate(st.session_state.get("discovery_hints", ())):
            columns = st.columns([1, 3, 1])
            if hint.preview_url:
                columns[0].image(hint.preview_url, caption="External discovery image")
            else:
                columns[0].markdown("No external thumbnail")
            columns[1].subheader(hint.target_name or "Unnamed tracker target")
            columns[1].caption(
                f"{', '.join(hint.instruments) or 'Unknown instrument'} - "
                f"{', '.join(hint.filters) or 'Unknown filter'} - proposal {hint.proposal_id or 'unknown'}"
            )
            columns[1].write(hint.notes or "No tracker title")
            columns[1].caption(f"Source: {hint.source_url}; credit: {hint.credit or 'not supplied'}")
            if columns[2].button("Use hint", key=f"tracker-use-{index}"):
                card = draft_from_discovery_hint(hint)
                _request_scene_replacement(card, None, saved=False)
                st.rerun()
    with tab_existing:
        choices = st.session_state.get("workspace_inputs", [])
        if not choices:
            st.info("No existing Galaxy artifacts were found.")
        for index, route in enumerate(choices):
            columns = st.columns([5, 1])
            columns[0].code(f"{route.kind}: {route.path}")
            if columns[1].button("Open", key=f"open-artifact-{index}"):
                st.session_state.pop("routed_input", None)
                _initialize_session(settings, route.path)
                st.rerun()


def _target_config(card: SceneCard):
    from galaxy.processing_config import TargetConfig
    if card.target is None:
        raise ValueError("target is incomplete")
    source = document(card.target)
    payload = {key: source[key] for key in ("name", "ra_deg", "dec_deg", "ra", "dec", "region")
               if key in source}
    return TargetConfig.model_validate(payload)


def _search_config(card: SceneCard) -> SearchConfig:
    payload = document(card.search) if card.search else {}
    if "max_total_observations" in payload:
        payload["max_total_observations"] = payload.pop("max_total_observations")
    return SearchConfig.model_validate(payload)


def _query_candidates(card: SceneCard) -> CandidateManifest:
    target = _target_config(card)
    search = _search_config(card)
    resolved = resolve_target(target)
    shape, values = region_to_mast_shape(target.region, resolved.coord)
    outcome = query_archive_outcome(shape, values, search)
    if outcome.status is ArchiveQueryStatus.FAILED:
        raise RuntimeError(f"MAST query failed: {outcome.message}")
    if outcome.status is ArchiveQueryStatus.INCOMPLETE:
        raise RuntimeError(f"MAST query incomplete: {outcome.message}")
    if outcome.result is None:
        raise RuntimeError("MAST query returned no result object")
    return build_candidate_manifest(outcome.result.candidates, search)


def _render_refinement(settings: ApplicationSettings) -> None:
    st.title("Scene refinement")
    card: SceneCard | None = st.session_state.get("active_card")
    if card is None:
        st.info("Choose a target or open a saved scene from Discovery.")
        return
    st.caption(card.target.resolved_name or card.target.name if card.target else card.title)
    data_tab, color_tab, frame_tab, artifacts_tab = st.tabs(["Data", "Color", "Frame", "Artifacts"])
    with data_tab:
        _render_data(card, settings)
    card = st.session_state["active_card"]
    with color_tab:
        _render_color(card)
    card = st.session_state["active_card"]
    with frame_tab:
        _render_frame(card)
    card = st.session_state["active_card"]
    with artifacts_tab:
        _render_artifacts(card, st.session_state.get("active_path"))
    left, middle, right = st.columns(3)
    save_label = _save_label("Save draft")
    if left.button(save_label, key="refinement-save"):
        _save_active(settings)
    issues = render_issues(card)
    if middle.button("Render", disabled=bool(issues), key="refinement-render"):
        st.session_state["screen"] = Screen.RENDER.value
        st.rerun()
    if right.button("Back to Discovery"):
        st.session_state["screen"] = Screen.DISCOVERY.value
        st.rerun()
    if issues:
        with st.expander(f"Render needs {len(issues)} correction(s)"):
            for issue in issues:
                st.write(f"{issue.path}: {issue.message}")


def _render_artifacts(card: SceneCard, card_path: Path | None) -> None:
    inventory = inspect_scene_artifacts(card, card_path)
    st.subheader("Artifact inventory")
    counts = {
        "Selected source products": len(inventory.sources),
        "Remote-only downloadable sources": inventory.remote_source_count,
        "Available local source assets": inventory.local_source_count,
        "Candidate-manifest assets": inventory.asset_count("candidate_manifest"),
        "Aligned-plane sets": inventory.asset_count("aligned_planes"),
        "Successful renders": len(inventory.renders),
        "Exports": inventory.export_count,
        "Missing or corrupt referenced assets": inventory.issue_count,
    }
    for label, count in counts.items():
        st.write(f"{label}: {count}")
    if inventory.sources:
        st.dataframe(pd.DataFrame([{
            "mission": item.mission or "unknown", "filter": item.filter_name or "unknown",
            "processing_level": item.processing_level or "unknown",
            "product_id": item.product_id, "filename": item.filename or "unknown",
            "status": item.status,
        } for item in inventory.sources]), use_container_width=True, hide_index=True)
    else:
        st.info("Selected source products: None created")
    generated = [item for item in inventory.assets if item.kind != "source"]
    if generated:
        st.dataframe(pd.DataFrame([{
            "asset_id": item.asset_id, "kind": item.kind, "status": item.status,
            "path": str(item.path) if item.path else "",
        } for item in generated]), use_container_width=True, hide_index=True)
    else:
        st.info("Generated artifacts: None created")
    if inventory.renders:
        st.dataframe(pd.DataFrame([{
            "render_id": item.render_id, "branch": item.branch,
            "revision": item.revision, "state": item.state,
        } for item in inventory.renders]), use_container_width=True, hide_index=True)
    else:
        st.info("Render history: None created")


def _render_data(card: SceneCard, settings: ApplicationSettings) -> None:
    manifest: CandidateManifest | None = st.session_state.get("candidate_manifest")
    if manifest is None:
        manifest = manifest_from_card(card)
    cache_directory = settings.scene_directory / ".discovery-cache"
    try:
        cached = load_cached_candidates(cache_directory, card)
    except (OSError, ValueError) as exc:
        cached = None
        st.warning(f"Cached archive result could not be read: {exc}")
    if cached is not None:
        freshness = "stale" if cached.stale else "fresh"
        st.caption(f"Cached MAST candidates: retrieved {cached.manifest.generated_at}; {freshness}.")
    force_refresh = st.checkbox(
        "Force a new MAST query", value=False, key="force-refresh",
        on_change=_widget_changed, args=("force-refresh",),
    )
    reuse_stale = st.checkbox(
        "Explicitly reuse stale cached candidates",
        value=False,
        key="reuse-stale",
        on_change=_widget_changed,
        args=("reuse-stale",),
        disabled=cached is None or not cached.stale,
    )
    if st.button("Query MAST observations and products"):
        try:
            st.session_state["operation_phase"] = OperationPhase.RUNNING.value
            can_reuse = cached is not None and not force_refresh and (not cached.stale or reuse_stale)
            if can_reuse:
                manifest = cached.manifest
                st.session_state["operation_message"] = (
                    f"Reused {'stale' if cached.stale else 'fresh'} cached candidates from "
                    f"{cached.manifest.generated_at}"
                )
            else:
                with st.spinner("Querying MAST"):
                    manifest = _query_candidates(card)
                save_cached_candidates(cache_directory, card, manifest)
                st.session_state["operation_message"] = (
                    f"Queried MAST and cached candidates at {manifest.generated_at}"
                )
            st.session_state["candidate_manifest"] = manifest
            st.session_state.pop("candidate-editor", None)
            st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
        except Exception as exc:
            st.session_state["operation_phase"] = OperationPhase.FAILED.value
            st.error(f"Archive query failed: {exc}")
            return
    if manifest is None:
        st.info("Query MAST to compare available observations and exact products.")
        return
    policy = manifest.selection_policy
    st.info(f"Recommended selection policy: {policy}. Apply is explicit; missing metadata is shown as unknown.")
    manifest = _candidate_editor(manifest)
    st.session_state["candidate_manifest"] = manifest
    if st.button("Apply selected products and recommended defaults"):
        try:
            updated = apply_manifest_selection(card, manifest)
            updated = materialize_render_defaults(updated)
            st.session_state["active_card"] = updated
            st.success("Exact product pins, filters, mapping, tone, and frame defaults applied.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _candidate_editor(manifest: CandidateManifest) -> CandidateManifest:
    rows = [{
        "include": item.selected, "observation": item.obs_id or item.obsid or "unknown",
        "date": item.observation_date_start or "unknown", "mission": item.mission or "unknown",
        "instrument": item.instrument or "unknown", "filter": item.filter_name or "unknown",
        "exposure_seconds": item.exposure_time if item.exposure_time is not None else "unknown",
        "product": item.product_filename or item.candidate_id,
        "recommendation_basis": item.auto_selection_reason,
        "candidate_id": item.candidate_id,
    } for item in manifest.candidates]
    edited = st.data_editor(
        pd.DataFrame(rows), use_container_width=True, hide_index=True,
        key="candidate-editor", on_change=_widget_changed, args=("candidate-editor",),
    )
    by_id = {item.candidate_id: item for item in manifest.candidates}
    for row in edited.to_dict("records"):
        by_id[str(row["candidate_id"])].user_selected = bool(row["include"])
    search = SearchConfig(
        observation_selection=manifest.selection_policy,
        max_observations_per_filter=manifest.max_observations_per_filter,
    )
    candidates = apply_selection_policy(manifest.candidates, search, manifest.selection_inputs)
    return CandidateManifest(
        generated_at=manifest.generated_at, config_path=manifest.config_path,
        selection_policy=manifest.selection_policy,
        max_observations_per_filter=manifest.max_observations_per_filter,
        selection_inputs=manifest.selection_inputs, candidates=candidates,
    )


def _render_color(card: SceneCard) -> None:
    if card.selection is None or not card.selection.selected_product_ids:
        st.info("Select data before defining color.")
        return
    if card.mapping is None or card.tone is None:
        st.info("No recommendation has been applied.")
        if st.button("Apply color and tone recommendation"):
            try:
                st.session_state["active_card"] = materialize_render_defaults(card)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        return
    st.caption("Continuum guidance orders enabled filters from blue to red. Every weight remains editable.")
    mapping = document(card.mapping)
    for index, entry in enumerate(mapping.get("planes", [])):
        label = str(entry.get("plane") or entry.get("filter"))
        columns = st.columns(4)
        columns[0].write(label)
        for column, channel in zip(columns[1:], ("red", "green", "blue")):
            entry["rgb"][channel] = column.number_input(
                channel.title(), value=float(entry["rgb"].get(channel, 0.0)),
                key=f"map-{index}-{channel}",
            )
    if mapping != document(card.mapping):
        st.session_state["active_card"] = edit_scene(card, {"mapping": mapping})


def _render_frame(card: SceneCard) -> None:
    if card.canvas is None:
        st.warning("The scene has no crop frame.")
        if st.button("Initialize default frame"):
            try:
                st.session_state["active_card"] = initialize_canvas(card)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        return
    canvas = document(card.canvas)
    center = canvas.setdefault("center", {"mode": "explicit"})
    left, right = st.columns(2)
    center["ra_deg"] = left.number_input("Center RA", value=float(center.get("ra_deg", 0.0)))
    center["dec_deg"] = right.number_input("Center Dec", value=float(center.get("dec_deg", 0.0)))
    canvas["width"] = int(left.number_input("Width (pixels)", min_value=1, value=int(canvas["width"])))
    canvas["height"] = int(right.number_input("Height (pixels)", min_value=1, value=int(canvas["height"])))
    canvas["pixel_scale_arcsec"] = left.number_input(
        "Pixel scale (arcsec)", min_value=0.000001, value=float(canvas["pixel_scale_arcsec"])
    )
    canvas["rotation_deg"] = right.number_input(
        "Rotation (degrees)", min_value=0.0, max_value=359.999999,
        value=float(canvas.get("rotation_deg", 0.0)),
    )
    if canvas != document(card.canvas):
        st.session_state["active_card"] = edit_scene(card, {"canvas": canvas})
    if st.button("Reset to target region"):
        try:
            st.session_state["active_card"] = initialize_canvas(card, reset=True)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    footprint_assets = [
        asset for asset in (card.assets or {}).values()
        if asset.kind == "footprint" and asset.path and st.session_state.get("active_path")
    ]
    for asset in footprint_assets[-1:]:
        path = asset_path(st.session_state["active_path"], asset)
        if path.is_file():
            st.image(str(path), caption="Selected-observation footprints and crop frame")
    st.caption("The crop frame is the output sky footprint; available footprint overlays do not guarantee full pixel coverage.")


def _render_render(settings: ApplicationSettings) -> None:
    st.title("Render and adjust")
    card: SceneCard | None = st.session_state.get("active_card")
    planes_path: Path | None = st.session_state.get("planes_path")
    if card is None and planes_path is not None:
        _render_aligned_planes(planes_path)
        return
    if card is None:
        st.info("Refine a scene before rendering.")
        return
    branches = ["original"]
    if card.psf and card.psf.enabled:
        branches.append("deconvolved")
    branch = st.selectbox("Processing branch", branches, key="render-branch")
    _render_current_image(card, st.session_state.get("active_path"), branch)
    with st.expander("Mapping and tone controls"):
        _render_color(card)
        card = st.session_state["active_card"]
        _render_tone(card)
        card = st.session_state["active_card"]
    problems = render_issues(card, branch)
    if problems:
        st.warning("This scene is not render-ready.")
        for problem in problems:
            st.write(f"{problem.path}: {problem.message}")
    job: RenderJob | None = st.session_state.get("render_job")
    snapshot = job.snapshot() if job is not None else None
    if snapshot is not None:
        st.session_state["operation_phase"] = snapshot.phase.value
        st.session_state["operation_message"] = snapshot.message or snapshot.stage
        if snapshot.stage:
            st.info(f"Stage: {snapshot.stage}")
        if snapshot.phase is OperationPhase.RUNNING:
            left_status, right_status = st.columns(2)
            if left_status.button("Cancel render"):
                job.cancel()
                st.session_state["operation_message"] = "Cancellation requested; waiting for a safe stage boundary"
            if right_status.button("Refresh render status"):
                st.rerun()
        elif snapshot.phase is OperationPhase.SUCCEEDED and snapshot.result is not None:
            if not st.session_state.get("render_job_applied"):
                try:
                    merged = merge_render_completion(card, snapshot.result.card)
                    st.session_state["active_card"] = merged
                    st.session_state["saved_document"] = document(snapshot.result.card)
                    st.session_state["render_job_applied"] = True
                    card = merged
                    st.success(snapshot.message)
                except ValueError as exc:
                    st.session_state["operation_phase"] = OperationPhase.FAILED.value
                    st.session_state["operation_message"] = str(exc)
                    st.error(f"Render completion was not attached: {exc}")
            else:
                st.success(snapshot.message)
        elif snapshot.phase is OperationPhase.CANCELLED:
            st.warning(f"{snapshot.message}. The previous successful preview was retained.")
        elif snapshot.phase is OperationPhase.FAILED:
            st.error(f"Render failed; the previous successful preview was retained: {snapshot.message}")
        if snapshot.phase in {OperationPhase.SUCCEEDED, OperationPhase.CANCELLED, OperationPhase.FAILED}:
            if st.button("Dismiss render status"):
                st.session_state["render_job"] = None
                st.session_state["render_job_applied"] = False
                st.rerun()
    running = snapshot is not None and snapshot.phase is OperationPhase.RUNNING
    if st.button("Generate preview", disabled=bool(problems) or running):
        if st.session_state.get("active_path") is None and not _save_active(settings):
            return
        st.session_state["render_job"] = start_render_job(st.session_state["active_path"])
        st.session_state["render_job_applied"] = False
        st.session_state["operation_phase"] = OperationPhase.RUNNING.value
        st.session_state["operation_message"] = "Render started"
        st.rerun()
    left, middle, right = st.columns(3)
    if left.button(_save_label("Save draft"), key="render-save"):
        _save_active(settings)
    if middle.button("Refine data or frame"):
        st.session_state["screen"] = Screen.REFINEMENT.value
        st.rerun()
    if right.button("Output options"):
        st.session_state["screen"] = Screen.OUTPUT.value
        st.rerun()


def _render_current_image(card: SceneCard, card_path: Path | None, branch: str) -> None:
    record = matching_render(card, branch)
    if record is None:
        if card.renders:
            st.warning("The last successful preview is out of date for the current scene settings.")
        else:
            st.info("No preview has been generated.")
        return
    if card_path is None:
        st.warning("The current preview has no associated scene path.")
        return
    image = asset_path(card_path, (card.assets or {})[record.image_asset_id])
    if image.is_file():
        st.image(str(image), caption=f"Galaxy preview - revision {record.content_revision}, {record.branch}")
    else:
        st.warning(f"Preview dependency is missing: {image}")


def _render_aligned_planes(path: Path) -> None:
    st.caption(f"Explicit aligned-plane input: {path}")
    try:
        records = load_multiplane_records(path)
        planes = {record.plane_id: record.data for record in records}
        metadata = {record.plane_id: record.metadata for record in records}
        mappings = default_plane_mappings(metadata)
        mapping = MappingConfig(planes=mappings)
        tone = ToneConfig(
            stretch=ToneStretchSet(**{c: StretchConfig(kind="asinh", parameter=4.0)
                                      for c in ("red", "green", "blue")}),
            percentiles=TonePercentiles(black=1.0, white=99.0),
            gain=ToneGainBias(red=1.0, green=1.0, blue=1.0),
            bias=ToneGainBias(red=0.0, green=0.0, blue=0.0),
            saturation=1.0,
        )
        composed = compose_channels(CompositionInputs(planes, metadata), mapping)
        image = apply_tone(composed, tone, bit_depth=16).astype(np.uint16)
        st.image(np.clip(image / 257.0, 0, 255).astype(np.uint8), caption="Aligned-plane preview")
        st.info("This artifact has no invented archive provenance. Save becomes available after creating a scene card.")
    except (OSError, ValueError) as exc:
        st.error(f"Aligned-plane preview failed: {exc}")


def _render_tone(card: SceneCard) -> None:
    if card.tone is None:
        st.info("Apply the recommendation in refinement before editing tone.")
        return
    tone = document(card.tone)
    percentiles = tone["percentiles"]
    left, right = st.columns(2)
    percentiles["black"] = left.number_input(
        "Black percentile", min_value=0.0, max_value=99.999,
        value=float(percentiles["black"]), key="render-black",
    )
    percentiles["white"] = right.number_input(
        "White percentile", min_value=0.001, max_value=100.0,
        value=float(percentiles["white"]), key="render-white",
    )
    tone["saturation"] = st.number_input(
        "Saturation", min_value=0.0, value=float(tone["saturation"]), key="render-saturation"
    )
    if tone != document(card.tone):
        try:
            st.session_state["active_card"] = edit_scene(card, {"tone": tone})
        except ValueError as exc:
            st.error(str(exc))


def _render_output(settings: ApplicationSettings) -> None:
    st.title("Output and save")
    card: SceneCard | None = st.session_state.get("active_card")
    if card is None:
        st.info("Open or refine a scene first.")
        return
    title = st.text_input("Scene title", value=card.title)
    if title.strip() and title != card.title:
        st.session_state["active_card"] = card = edit_scene(card, {"title": title.strip()})
    output_format = st.radio(
        "Format", ["png", "tiff"], horizontal=True, key="output-format",
        on_change=_widget_changed, args=("output-format",),
    )
    if card.canvas is not None and card.canvas.width and card.canvas.height:
        left, right = st.columns(2)
        width = int(left.number_input("Output width", min_value=1, value=card.canvas.width))
        height = int(right.number_input("Output height", min_value=1, value=card.canvas.height))
        if st.button("Apply output dimensions"):
            try:
                st.session_state["active_card"] = resize_canvas(card, width, height)
                st.success("Dimensions applied; sky extent was preserved by adjusting pixel scale.")
                st.rerun()
            except ValueError as exc:
                st.error(f"{exc}. Change the frame in Scene refinement.")
    destination = st.text_input(
        "Export destination",
        value=str(settings.project_root / "artifacts" / f"{default_scene_path(card, settings.scene_directory).stem}.{output_format}"),
    )
    overwrite = st.checkbox(
        "Overwrite an existing image", key="output-overwrite",
        on_change=_widget_changed, args=("output-overwrite",),
    )
    save_column, export_column = st.columns(2)
    if save_column.button(_save_label("Save scene")):
        _save_active(settings)
    if export_column.button("Export image"):
        card_path = st.session_state.get("active_path")
        if card_path is None:
            st.error("Save the scene before exporting.")
        else:
            try:
                updated = export_current_render(
                    card, card_path, destination, output_format=output_format, overwrite=overwrite
                )
                st.session_state["active_card"] = updated
                st.session_state["saved_document"] = document(updated)
                st.success(f"Image exported to {destination}")
            except Exception as exc:
                st.error(f"Image export failed independently of scene save: {exc}")
    if st.button("Back to Render"):
        st.session_state["screen"] = Screen.RENDER.value
        st.rerun()


def _render_library(settings: ApplicationSettings) -> None:
    st.title("Projects and scenes")
    st.caption(str(settings.scene_directory))
    try:
        library = list_project_library(settings.scene_directory, settings.project_root)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.header("Examples")
    _render_library_entries(library.examples, settings, "example")
    st.header("Saved scenes")
    if not library.saved_scenes:
        st.info("No saved scenes yet. Start in Discovery or save an example as a new scene.")
    _render_library_entries(library.saved_scenes, settings, "saved")
    if st.button("Back to Discovery", key="library-discovery"):
        st.session_state["screen"] = Screen.DISCOVERY.value
        st.rerun()


def _render_library_entries(
    entries: tuple[LibraryEntry, ...], settings: ApplicationSettings, group: str
) -> None:
    for index, entry in enumerate(entries):
        if entry.card is None:
            st.error(f"{entry.path.name}: invalid scene card - {entry.error}")
            continue
        columns = st.columns([1, 3, 1, 1])
        if entry.thumbnail_path:
            columns[0].image(str(entry.thumbnail_path), caption=entry.thumbnail_kind)
        else:
            columns[0].markdown("No thumbnail")
        columns[1].subheader(entry.card.title)
        target = entry.card.target
        target_label = (
            target.resolved_name or target.name
            if target is not None else None
        ) or "Target not set"
        origin_label = "Bundled example" if entry.origin is LibraryOrigin.BUNDLED_EXAMPLE else "User scene"
        columns[1].caption(
            f"{origin_label} - {target_label} - {entry.readiness_label} - "
            f"saved {entry.card.updated_at} - {entry.thumbnail_kind}"
        )
        if entry.dependencies:
            columns[1].warning(
                "Missing dependencies: " + ", ".join(issue.asset_id for issue in entry.dependencies)
            )
        if columns[2].button("Open", key=f"library-open-{group}-{index}"):
            _request_scene_replacement(
                entry.card, entry.path, saved=True, origin=entry.origin
            )
            st.rerun()
        if columns[3].button("Duplicate", key=f"library-copy-{group}-{index}"):
            try:
                copied, _ = duplicate_library_scene(entry, settings.scene_directory)
                _request_scene_replacement(copied, None, saved=False)
                st.rerun()
            except (OSError, ValueError) as exc:
                st.error(f"Duplicate failed: {exc}")


if __name__ == "__main__":  # Streamlit executes this file as the application script.
    main()

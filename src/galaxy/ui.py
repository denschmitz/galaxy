"""Streamlit UI for the five-screen JSON scene-card workflow."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from galaxy.background import (
    BackgroundSamplingError, apply_background, background_masks, background_overlay_array,
    background_selection_key, estimate_background,
)
from galaxy.app_config import ApplicationConfigError, ApplicationSettings, load_application_settings, parse_ui_startup_args
from galaxy.discovery_sources import (
    DiscoverySourceQuery, YuvalHarpazLatestReleaseSource, discover_isolated,
)
from galaxy.discovery_cache import (
    candidate_cache_directory,
    load_cached_candidates,
    save_cached_candidates,
)
from galaxy.mapping import default_plane_mappings
from galaxy.normalization_reference import estimate_normalization_references
from galaxy.mast import ArchiveQueryStatus, apply_selection_policy, build_candidate_manifest, query_archive_outcome
from galaxy.planes import load_multiplane_records
from galaxy.rendering import render_aligned_planes
from galaxy.processing_config import (
    BackgroundConfig, BackgroundEstimatorConfig, CoverageConfig, MappingConfig, SearchConfig,
    SkyRectangleConfig, StretchConfig, ToneConfig, ToneGainBias, TonePercentiles,
    ToneStretchSet,
)
from galaxy.scene_card import asset_path, create_scene, document, edit_scene, load_scene
from galaxy.scene_models import SceneCard
from galaxy.render_jobs import RenderJob, request_cancellation_before_departure, start_render_job
from galaxy.scene_workflow import (
    LibraryEntry, LibraryOrigin, OperationPhase, Screen, apply_manifest_selection,
    associated_asset_root, default_scene_path, delete_library_scene,
    discover_workspace_inputs, draft_from_discovery_hint, draft_from_resolver_match,
    draft_from_target, duplicate_library_scene, example_user_path,
    export_current_render, initialize_canvas, inspect_scene_artifacts, list_project_library, matching_render,
    manifest_from_card, manifest_from_scene_asset, materialize_render_defaults, persist_candidate_manifest,
    render_issues, resolve_workdir_input, resize_canvas,
    materialize_example, merge_render_completion, open_example_user_copy, save_draft,
    selected_fits_paths,
)
from galaxy.selection import CandidateManifest, CandidateRecord, load_candidate_manifest
from galaxy.selection_guidance import (
    MISSION_SCOPES, SELECTION_MODES, apply_selection_mode, clear_selection,
    grouped_candidates, recommendation_explanation, selection_summary as guidance_summary,
    set_custom_selection,
)
from galaxy.targeting import ResolverOutcome, ResolverStatus, region_to_mast_shape, resolve_name, resolve_target
from galaxy.tone import propose_auto_stretch
from galaxy.viewport_framing import ViewportFitResult, fit_fits_paths, render_fit_preview


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
        if route.path.parent == (settings.project_root / "examples").resolve():
            card, path = open_example_user_copy(route.path, settings.scene_directory)
            _set_active_scene(card, path, saved=True)
        else:
            _set_active_scene(load_scene(route.path), route.path, saved=True)
    elif route.kind == "manifest":
        manifest = load_candidate_manifest(route.path)
        card = _card_for_manifest(manifest)
        _set_active_scene(card, None, saved=False)
        st.session_state["candidate_manifest"] = manifest
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
    for key in list(st.session_state):
        if key.startswith("bridge-enabled-"):
            st.session_state.pop(key, None)
    st.session_state["active_card"] = card
    st.session_state["active_path"] = path
    st.session_state["saved_document"] = document(card) if saved else None
    st.session_state["active_origin"] = origin.value
    st.session_state["planes_path"] = None
    st.session_state["candidate_manifest"] = None
    st.session_state.pop("candidate_manifest_error", None)
    if path is not None:
        try:
            st.session_state["candidate_manifest"] = manifest_from_scene_asset(card, path)
        except (OSError, ValueError) as exc:
            st.session_state["candidate_manifest_error"] = str(exc)
    st.session_state["screen"] = Screen.REFINEMENT.value
    for key in (
        "candidate-editor", "candidate-group-editor", "candidate-alternative-editor",
        "candidate-group-choice", "selection-mode", "mission-scope", "render-branch",
        "output-overwrite", "pending_project_delete", "pending_viewport_fit",
    ):
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


def _render_launch_needs_save(
    card: SceneCard, active_path: Path | None, saved_document: dict[str, Any] | None,
) -> bool:
    return active_path is None or document(card) != saved_document


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
        "render-branch", "output-overwrite", "pending_project_delete", "pending_viewport_fit",
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
    return default


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


def _render_bridge(card: SceneCard) -> None:
    job: RenderJob | None = st.session_state.get("render_job")
    running = job is not None and job.snapshot().phase is OperationPhase.RUNNING
    current = card.bridge.enabled if card.bridge is not None else True
    selected = st.toggle(
        "Bridge small NaN holes", value=current, disabled=running,
        key=f"bridge-enabled-{card.scene_id}",
        help=("On estimates eligible small enclosed bright-core holes for presentation. "
              "Off preserves strict missing data. Changing this setting requires reprojection; "
              "rejected holes remain invalid."),
    )
    if not running and selected != current:
        st.session_state["active_card"] = edit_scene(card, {"bridge": {"enabled": selected}})
        card = st.session_state["active_card"]
    if card.renders and matching_render(card) is None:
        st.caption("Preview is out of date. Generate preview to reproject with the current bridge setting.")


def _render_refinement(settings: ApplicationSettings) -> None:
    st.title("Scene refinement")
    card: SceneCard | None = st.session_state.get("active_card")
    if card is None:
        st.info("Choose a target or open a saved scene from Discovery.")
        return
    _render_bridge(card)
    card = st.session_state["active_card"]
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
        if card.selection is None or not card.selection.selected_product_ids:
            st.info("Next steps")
            st.markdown(
                "1. Choose a selection mode and scope\n"
                "2. Review the proposed products\n"
                "3. Apply the selection\n"
                "4. Review color and frame\n"
                "5. Render"
            )
        elif card.mapping is None or card.tone is None:
            st.info("Next: apply the recommended color, tone, and frame defaults.")
        else:
            st.warning("Review the remaining setup items before rendering.")
        with st.expander("Technical readiness details"):
            st.caption(f"{len(issues)} field-level correction(s)")
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
    for warning in inventory.warnings:
        st.warning(warning)
    if inventory.sources:
        st.dataframe(pd.DataFrame([{
            "mission": item.mission or "unknown", "filter": item.filter_name or "unknown",
            "processing_level": item.processing_level or "unknown",
            "product_id": item.product_id, "filename": item.filename or "unknown",
            "native_unit": item.native_unit or "unknown",
            "mask_sources": ", ".join(item.mask_sources) if item.mask_sources else "none",
            "normalization": item.normalization_mode,
            "black_percentile": item.black_percentile if item.black_percentile is not None else "unknown",
            "white_percentile": item.white_percentile if item.white_percentile is not None else "unknown",
            "plane_gain": item.plane_gain,
            "valid_coverage": (
                f"{item.valid_coverage_fraction:.1%}"
                if item.valid_coverage_fraction is not None else "unknown"
            ),
            "rgb_contribution": _format_rgb_contribution(item.rgb_contribution_percent),
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


def _format_rgb_contribution(value: dict[str, float] | None) -> str:
    if not value:
        return "unknown"
    return " / ".join(
        f"{channel[0].upper()} {float(value.get(channel, 0.0)):.1f}%"
        for channel in ("red", "green", "blue")
    )


def _render_data(card: SceneCard, settings: ApplicationSettings) -> None:
    manifest: CandidateManifest | None = st.session_state.get("candidate_manifest")
    persist_manifest = manifest is not None
    if manifest is None:
        manifest = manifest_from_card(card)
    if st.session_state.get("candidate_manifest_error"):
        st.warning(f"Saved candidate list is unavailable: {st.session_state['candidate_manifest_error']}")
    cache_directory = candidate_cache_directory(settings.scene_directory)
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
        "Explicitly reuse stale cached candidates", value=False, key="reuse-stale",
        on_change=_widget_changed, args=("reuse-stale",),
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
            scene_path = st.session_state.get("active_path") or default_scene_path(card, settings.scene_directory)
            card, _ = persist_candidate_manifest(card, scene_path, manifest)
            st.session_state["active_card"] = card
            st.session_state["candidate_manifest"] = manifest
            for key in ("candidate-group-editor", "candidate-alternative-editor"):
                st.session_state.pop(key, None)
            st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
        except Exception as exc:
            st.session_state["operation_phase"] = OperationPhase.FAILED.value
            st.error(f"Archive query failed: {exc}")
            return
    if manifest is None:
        st.info("Query MAST to compare available observations and exact products.")
        return

    mode = st.radio(
        "Selection mode", list(SELECTION_MODES),
        index=list(SELECTION_MODES).index(manifest.selection_mode),
        format_func=SELECTION_MODES.get, key="selection-mode",
    )
    available_missions = {str(item.mission or "").upper() for item in manifest.candidates}
    scope_options = [
        key for key in MISSION_SCOPES
        if key == "all" or key.upper() in available_missions
    ]
    if manifest.mission_scope not in scope_options:
        manifest = apply_selection_mode(manifest, mode, "all")
    scope = st.radio(
        "Mission scope", scope_options,
        index=scope_options.index(manifest.mission_scope),
        format_func=MISSION_SCOPES.get, key="mission-scope", horizontal=True,
    )
    if mode != manifest.selection_mode or scope != manifest.mission_scope:
        manifest = apply_selection_mode(manifest, mode, scope)
    st.caption(
        "Preview is a quick-look subset. Full filter set keeps one recommended product "
        "per mission, instrument, and filter. Custom keeps exact manual choices."
    )
    available_missions = {str(item.mission or "").upper() for item in manifest.candidates}
    for required_mission in ("HST", "JWST"):
        if required_mission not in available_missions:
            st.caption(f"{required_mission} scope unavailable: no matching candidates found.")
    summary_slot = st.empty()
    manifest = _guided_candidate_editor(manifest)
    summary = guidance_summary(manifest)
    unknown_suffix = (
        f" · {summary.unknown_size_products} unknown sizes"
        if summary.unknown_size_products else ""
    )
    summary_slot.write(
        f"{summary.mode_label} · {summary.selected_products} products · "
        f"{summary.filter_count} filters · {summary.mission_count} missions · "
        f"{summary.instrument_count} instruments · "
        f"{_format_download_size(summary.known_download_bytes)}{unknown_suffix}"
    )
    st.caption(f"{summary.available_products} unique products available in {len(grouped_candidates(manifest))} groups.")
    clear_col, restore_col = st.columns(2)
    if clear_col.button("Clear selection"):
        manifest = clear_selection(manifest)
        st.session_state["candidate_manifest"] = manifest
        st.rerun()
    if restore_col.button("Restore mode recommendation"):
        restore_mode = mode if mode != "custom" else manifest.recommendation_mode
        manifest = apply_selection_mode(manifest, restore_mode, scope)
        st.session_state["candidate_manifest"] = manifest
        st.rerun()

    if persist_manifest:
        scene_path = st.session_state.get("active_path") or default_scene_path(card, settings.scene_directory)
        card, _ = persist_candidate_manifest(card, scene_path, manifest)
        st.session_state["active_card"] = card
        st.session_state["candidate_manifest"] = manifest
    if summary.selected_products == 0:
        st.warning("Select at least one product before applying the recommendation.")
    if st.button(
        "Apply selection and recommended defaults", disabled=summary.selected_products == 0,
    ):
        try:
            updated = apply_manifest_selection(card, manifest)
            updated = materialize_render_defaults(updated, replace_existing=True)
            st.session_state["active_card"] = updated
            st.session_state.pop("pending_viewport_fit", None)
            st.success("Exact product pins, filters, mapping, tone, and frame defaults applied.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _guided_candidate_editor(manifest: CandidateManifest) -> CandidateManifest:
    groups = grouped_candidates(manifest)
    rows = [{
        "include": group.recommended.selected,
        "mission": group.key[0], "instrument": group.key[1], "filter": group.key[2],
        "recommended_product": group.recommended.product_filename or group.recommended.candidate_id,
        "alternatives": len(group.alternatives),
        "why": recommendation_explanation(group.recommended),
        "candidate_id": group.recommended.candidate_id,
    } for group in groups]
    edited = st.data_editor(
        pd.DataFrame(rows), use_container_width=True, hide_index=True,
        key="candidate-group-editor", on_change=_widget_changed, args=("candidate-group-editor",),
    )
    selected_ids = {item.candidate_id for item in manifest.candidates if item.selected}
    changed = False
    for row in edited.to_dict("records"):
        candidate_id = str(row["candidate_id"])
        include = bool(row["include"])
        if include != (candidate_id in selected_ids):
            changed = True
        if include:
            selected_ids.add(candidate_id)
        else:
            selected_ids.discard(candidate_id)

    alternative_groups = [group for group in groups if group.alternatives]
    if alternative_groups:
        labels = {
            " | ".join(group.key): group for group in alternative_groups
        }
        choice = st.selectbox("Inspect alternatives for", list(labels), key="candidate-group-choice")
        chosen = labels[choice]
        with st.expander(f"Show {len(chosen.alternatives)} alternatives — {choice}"):
            alternative_rows = [{
                "include": item.selected,
                "product": item.product_filename or item.candidate_id,
                "exposure_seconds": item.exposure_time if item.exposure_time is not None else "unknown",
                "size_bytes": item.file_size if item.file_size is not None else "unknown",
                "why": recommendation_explanation(item),
                "candidate_id": item.candidate_id,
            } for item in chosen.alternatives]
            alternatives = st.data_editor(
                pd.DataFrame(alternative_rows), use_container_width=True, hide_index=True,
                key="candidate-alternative-editor", on_change=_widget_changed,
                args=("candidate-alternative-editor",),
            )
            for row in alternatives.to_dict("records"):
                candidate_id = str(row["candidate_id"])
                include = bool(row["include"])
                if include != (candidate_id in selected_ids):
                    changed = True
                if include:
                    selected_ids.add(candidate_id)
                else:
                    selected_ids.discard(candidate_id)
    return set_custom_selection(manifest, selected_ids) if changed else manifest


def _format_download_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"

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
        canvas["frame_origin"] = "user"
        st.session_state["active_card"] = edit_scene(card, {"canvas": canvas})
        st.session_state.pop("pending_viewport_fit", None)
        card = st.session_state["active_card"]
    active_path = st.session_state.get("active_path")
    if st.button("Fit selected scans"):
        if active_path is None:
            st.error("Save the scene before fitting downloaded scans.")
        else:
            paths, identities, errors = selected_fits_paths(card, active_path)
            if errors:
                st.error("Selected footprints are not inspectable: " + "; ".join(errors))
            else:
                try:
                    st.session_state["pending_viewport_fit"] = fit_fits_paths(paths, identities)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    pending: ViewportFitResult | None = st.session_state.get("pending_viewport_fit")
    if pending is not None and not hasattr(pending, "boundaries_deg"):
        st.session_state.pop("pending_viewport_fit", None)
        pending = None
        st.info("The fit-preview format changed. Run Fit selected scans again to rebuild it.")
    if pending is not None:
        diagnostics = pending.diagnostics
        st.subheader("Fitted-frame preview")
        st.write(
            f"{diagnostics.width} x {diagnostics.height} pixels at "
            f"{diagnostics.pixel_scale_arcsec:.4f} arcsec/pixel; "
            f"{diagnostics.frame_width_deg * 60:.2f} x "
            f"{diagnostics.frame_height_deg * 60:.2f} arcmin"
        )
        st.caption(
            f"Components: {diagnostics.component_count}; span: "
            f"{diagnostics.angular_span_deg:.3f} deg; fill: "
            f"{diagnostics.fill_fraction:.1%}; estimated memory: "
            f"{diagnostics.estimated_memory_bytes / (1024 ** 2):.1f} MiB"
        )
        center_data = pending.canvas["center"]
        st.caption(
            f"Center: {float(center_data['ra_deg']):.6f}, "
            f"{float(center_data['dec_deg']):.6f} deg; rotation: "
            f"{float(pending.canvas['rotation_deg']):.2f} deg; selected products: "
            f"{len(pending.product_ids)}"
        )
        try:
            st.image(
                render_fit_preview(pending),
                caption="Proposed selected-FITS boundaries and fitted canvas border",
            )
        except ValueError as exc:
            st.error(f"Fitted-frame visualization failed: {exc}")
        for warning in pending.warnings:
            st.warning(warning)
        if pending.warnings:
            st.info("Revise the selection, continue with this fitted canvas, or keep the current canvas.")
        apply_column, keep_column = st.columns(2)
        if apply_column.button("Apply fitted canvas"):
            current: SceneCard = st.session_state["active_card"]
            st.session_state["active_card"] = edit_scene(current, {"canvas": pending.canvas})
            st.session_state.pop("pending_viewport_fit", None)
            st.rerun()
        if keep_column.button("Keep current canvas"):
            st.session_state.pop("pending_viewport_fit", None)
            st.rerun()
    if st.button("Reset to target region"):
        try:
            st.session_state["active_card"] = initialize_canvas(card, reset=True)
            st.session_state.pop("pending_viewport_fit", None)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    current_footprint = _current_footprint_path(card, active_path)
    if pending is None and current_footprint is not None:
        st.image(str(current_footprint), caption="Current rendered footprints and crop frame")
    elif pending is None and any(
        render.footprint_asset_id for render in (card.renders or [])
    ):
        st.info("The stored footprint overlay is stale for this canvas. Generate a new preview to update it.")
    st.caption("The crop frame is the output sky footprint; available footprint overlays do not guarantee full pixel coverage.")


def _current_footprint_path(card: SceneCard, card_path: Path | None) -> Path | None:
    if card_path is None:
        return None
    render = matching_render(card)
    if render is None or render.footprint_asset_id is None:
        return None
    asset = (card.assets or {}).get(render.footprint_asset_id)
    if asset is None or asset.kind != "footprint" or asset.path is None:
        return None
    path = asset_path(card_path, asset)
    return path if path.is_file() else None


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
        _render_tone(card, st.session_state.get("active_path"), branch)
        card = st.session_state["active_card"]
    with st.expander("Background pedestal"):
        _render_background(card, st.session_state.get("active_path"), branch)
        card = st.session_state["active_card"]
    with st.expander("Coverage and normalization reference"):
        _render_coverage(card, st.session_state.get("active_path"), branch)
        card = st.session_state["active_card"]
        _render_normalization_reference(card, st.session_state.get("active_path"), branch)
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
                    if (
                        snapshot.result.card.content_revision > card.content_revision
                        and document(card) == st.session_state.get("saved_document")
                    ):
                        merged = snapshot.result.card
                    else:
                        merged = merge_render_completion(card, snapshot.result.card)
                    st.session_state["active_card"] = merged
                    st.session_state["saved_document"] = document(snapshot.result.card)
                    st.session_state["render_job_applied"] = True
                    st.rerun()  # Redraw the preview from the newly attached live card.
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
        if _render_launch_needs_save(
            card,
            st.session_state.get("active_path"),
            st.session_state.get("saved_document"),
        ) and not _save_active(settings):
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
        image = render_aligned_planes(records, mapping, tone, bit_depth=16).rgb.astype(np.uint16)
        st.image(np.clip(image / 257.0, 0, 255).astype(np.uint8), caption="Aligned-plane preview")
        st.info("This artifact has no invented archive provenance. Save becomes available after creating a scene card.")
    except (OSError, ValueError) as exc:
        st.error(f"Aligned-plane preview failed: {exc}")


def _render_coverage(card: SceneCard, card_path: Path | None, branch: str) -> None:
    current = document(card.coverage) if card.coverage is not None else {
        "policy": "available_contributors", "tone_reference": "common_required_bands",
        "crop": "none", "padding_pixels": 0,
    }
    policy = st.selectbox(
        "Output footprint",
        ["available_contributors", "common_required_bands"],
        index=0 if current.get("policy") == "available_contributors" else 1,
        key="coverage-policy",
    )
    tone_reference = st.selectbox(
        "Brightness reference pixels",
        ["common_required_bands", "output_support"],
        index=(
            0 if current.get("tone_reference", "common_required_bands")
            == "common_required_bands" else 1
        ),
        key="coverage-tone-reference",
    )
    crop = st.selectbox(
        "Support crop", ["none", "bounding_box"],
        index=0 if current.get("crop") == "none" else 1,
        key="coverage-crop",
    )
    padding = int(st.number_input(
        "Crop padding (pixels)", min_value=0,
        value=int(current.get("padding_pixels", 0)), key="coverage-padding",
    ))
    proposal = CoverageConfig(
        policy=policy, tone_reference=tone_reference, crop=crop, padding_pixels=padding,
    )
    aligned_path = _latest_aligned_path(card, card_path, branch)
    preview_col, apply_col = st.columns(2)
    if preview_col.button("Preview coverage policy", key="coverage-preview"):
        if aligned_path is None:
            st.error("Generate a baseline preview with aligned planes before previewing coverage.")
        else:
            try:
                rendered = render_aligned_planes(
                    load_multiplane_records(aligned_path),
                    MappingConfig.model_validate(document(card.mapping)),
                    ToneConfig.model_validate(document(card.tone)),
                    bit_depth=16,
                    background=BackgroundConfig.model_validate(
                        document(card.background) if card.background is not None else {}
                    ),
                    coverage=proposal,
                )
                st.session_state["coverage_proposal"] = {
                    "branch": branch, "aligned_path": str(aligned_path),
                    "config": proposal, "result": rendered,
                }
            except (OSError, ValueError, BackgroundSamplingError) as exc:
                st.session_state.pop("coverage_proposal", None)
                st.error(f"Coverage preview is unsupported: {exc}")
    context = st.session_state.get("coverage_proposal")
    valid = (
        isinstance(context, dict) and context.get("branch") == branch
        and aligned_path is not None and context.get("aligned_path") == str(aligned_path)
        and context.get("config") == proposal
    )
    if valid:
        result = context["result"]
        st.image(
            np.clip(result.rgb / 257.0, 0, 255).astype(np.uint8),
            caption="Coverage-policy candidate",
        )
        st.json(result.coverage.diagnostics)
        if apply_col.button("Apply coverage policy", key="coverage-apply"):
            st.session_state["active_card"] = edit_scene(
                card, {"coverage": proposal.model_dump(mode="json")}
            )
            st.success("Coverage policy applied. Prior renders are now stale until regenerated.")
    else:
        apply_col.button("Apply coverage policy", key="coverage-apply", disabled=True)


def _render_normalization_reference(
    card: SceneCard, card_path: Path | None, branch: str,
) -> None:
    st.caption(
        "A region reference resolves locked per-plane bounds from the persisted background region; "
        "crop and viewport changes do not recompute them."
    )
    left, right = st.columns(2)
    black = float(left.number_input(
        "Reference black percentile", min_value=0.0, max_value=99.999,
        value=0.5, key="normalization-reference-black",
    ))
    white = float(right.number_input(
        "Reference white percentile", min_value=0.001, max_value=100.0,
        value=99.5, key="normalization-reference-white",
    ))
    aligned_path = _latest_aligned_path(card, card_path, branch)
    preview_col, apply_col = st.columns(2)
    if preview_col.button("Preview normalization reference", key="normalization-reference-preview"):
        if aligned_path is None:
            st.error("Generate a baseline preview with aligned planes before resolving a reference.")
        else:
            try:
                planes = load_multiplane_records(aligned_path)
                background = BackgroundConfig.model_validate(
                    document(card.background) if card.background is not None else {}
                )
                corrected = apply_background(planes, background).planes
                coverage = CoverageConfig.model_validate(
                    document(card.coverage) if card.coverage is not None else {}
                )
                proposal = estimate_normalization_references(
                    corrected, background, coverage,
                    black_percentile=black, white_percentile=white,
                )
                st.session_state["normalization_reference_proposal"] = {
                    "branch": branch, "aligned_path": str(aligned_path),
                    "black": black, "white": white, "planes": corrected,
                    "proposal": proposal,
                }
            except (OSError, ValueError, BackgroundSamplingError) as exc:
                st.session_state.pop("normalization_reference_proposal", None)
                st.error(f"Normalization reference is unsupported: {exc}")
    context = st.session_state.get("normalization_reference_proposal")
    valid = (
        isinstance(context, dict) and context.get("branch") == branch
        and aligned_path is not None and context.get("aligned_path") == str(aligned_path)
        and context.get("black") == black and context.get("white") == white
    )
    if valid:
        proposal = context["proposal"]
        st.dataframe(pd.DataFrame([
            {"plane": plane_id, **reference.model_dump(mode="json")}
            for plane_id, reference in proposal.references.items()
        ]), use_container_width=True)
        if apply_col.button("Apply normalization reference", key="normalization-reference-apply"):
            mapping = _mapping_with_reference_bounds(
                document(card.mapping), context["planes"], proposal.references,
            )
            st.session_state["active_card"] = edit_scene(card, {"mapping": mapping})
            st.success("Locked normalization reference applied. Prior renders are now stale.")
    else:
        apply_col.button(
            "Apply normalization reference", key="normalization-reference-apply", disabled=True,
        )


def _mapping_with_reference_bounds(
    mapping: dict[str, Any], planes: list[Any], references: dict[str, Any],
) -> dict[str, Any]:
    result = {**mapping, "planes": []}
    metadata = {plane.plane_id: plane.metadata for plane in planes}
    for entry in mapping.get("planes", []):
        if entry.get("plane"):
            targets = [entry["plane"]]
        else:
            requested = str(entry.get("filter") or "").upper()
            targets = [
                plane_id for plane_id, values in metadata.items()
                if str(values.get("filter") or "").upper() == requested
            ]
        if not targets:
            raise ValueError(f"normalization reference cannot resolve mapping selector {entry}")
        for plane_id in targets:
            reference = references.get(plane_id)
            if reference is None:
                raise ValueError(f"normalization reference is missing plane '{plane_id}'")
            updated = {key: value for key, value in entry.items() if key != "filter"}
            updated["plane"] = plane_id
            previous = dict(entry.get("normalization") or {})
            updated["normalization"] = {
                **previous,
                "mode": "fixed_bounds",
                "black_value": reference.black_value,
                "white_value": reference.white_value,
                "reference": reference.model_dump(mode="json"),
            }
            result["planes"].append(updated)
    return result


def _render_background(card: SceneCard, card_path: Path | None, branch: str) -> None:
    current = document(card.background) if card.background is not None else {}
    current_regions = current.get("inclusion_regions", [])
    current_exclusions = current.get("exclusion_regions", [])
    canvas = card.canvas
    center = canvas.center if canvas is not None else None
    default_ra = float(current_regions[0]["center_ra_deg"]) if current_regions else float(center.ra_deg or 0)
    default_dec = float(current_regions[0]["center_dec_deg"]) if current_regions else float(center.dec_deg or 0)
    default_width = (
        float(current_regions[0]["width_arcsec"]) if current_regions
        else max(1.0, float((canvas.width or 1) * (canvas.pixel_scale_arcsec or 1)) * 0.25)
    )
    default_height = (
        float(current_regions[0]["height_arcsec"]) if current_regions
        else max(1.0, float((canvas.height or 1) * (canvas.pixel_scale_arcsec or 1)) * 0.25)
    )
    st.caption(
        "Green marks the sky proposal, bright green marks common valid samples, and red marks exclusions."
    )
    left, right = st.columns(2)
    ra = left.number_input("Sky center RA (deg)", min_value=0.0, max_value=359.999999,
                           value=default_ra, key="background-ra")
    dec = right.number_input("Sky center Dec (deg)", min_value=-90.0, max_value=90.0,
                             value=default_dec, key="background-dec")
    width = left.number_input("Sky width (arcsec)", min_value=0.001,
                              value=default_width, key="background-width")
    height = right.number_input("Sky height (arcsec)", min_value=0.001,
                                value=default_height, key="background-height")
    use_exclusion = st.checkbox(
        "Exclude a protected source rectangle", value=bool(current_exclusions),
        key="background-use-exclusion",
    )
    exclusions: list[SkyRectangleConfig] = []
    if use_exclusion:
        existing = current_exclusions[0] if current_exclusions else {}
        ex_left, ex_right = st.columns(2)
        ex_ra = ex_left.number_input(
            "Exclusion center RA (deg)", min_value=0.0, max_value=359.999999,
            value=float(existing.get("center_ra_deg", ra)), key="background-exclusion-ra",
        )
        ex_dec = ex_right.number_input(
            "Exclusion center Dec (deg)", min_value=-90.0, max_value=90.0,
            value=float(existing.get("center_dec_deg", dec)), key="background-exclusion-dec",
        )
        ex_width = ex_left.number_input(
            "Exclusion width (arcsec)", min_value=0.001,
            value=float(existing.get("width_arcsec", max(1.0, width * 0.25))),
            key="background-exclusion-width",
        )
        ex_height = ex_right.number_input(
            "Exclusion height (arcsec)", min_value=0.001,
            value=float(existing.get("height_arcsec", max(1.0, height * 0.25))),
            key="background-exclusion-height",
        )
        exclusions.append(SkyRectangleConfig(
            region_id="protected-source", center_ra_deg=ex_ra, center_dec_deg=ex_dec,
            width_arcsec=ex_width, height_arcsec=ex_height,
        ))
    estimator_data = current.get("estimator", {})
    clip_sigma = st.number_input(
        "Clip sigma", min_value=0.001,
        value=float(estimator_data.get("clip_sigma", 3.0)), key="background-clip-sigma",
    )
    minimum_samples = int(st.number_input(
        "Minimum common samples", min_value=1,
        value=int(estimator_data.get("minimum_samples", 256)), step=1,
        key="background-minimum-samples",
    ))
    minimum_fraction = st.number_input(
        "Minimum common-valid fraction", min_value=0.001, max_value=1.0,
        value=float(estimator_data.get("minimum_valid_fraction", 0.5)),
        key="background-minimum-fraction",
    )
    policy = st.selectbox(
        "Black reference policy", ["corrected_zero", "legacy_percentile"],
        index=(
            0 if current.get("mode") != "pedestal"
            or current.get("black_reference_policy") == "corrected_zero" else 1
        ),
        key="background-black-policy",
    )
    proposal_config = BackgroundConfig(
        mode="pedestal",
        black_reference_policy=policy,
        inclusion_regions=[SkyRectangleConfig(
            region_id="sky", center_ra_deg=ra, center_dec_deg=dec,
            width_arcsec=width, height_arcsec=height,
        )],
        exclusion_regions=exclusions,
        estimator=BackgroundEstimatorConfig(
            clip_sigma=clip_sigma,
            max_iterations=int(estimator_data.get("max_iterations", 5)),
            minimum_samples=minimum_samples,
            minimum_valid_fraction=minimum_fraction,
        ),
    )
    aligned_path = _latest_aligned_path(card, card_path, branch)
    preview_column, apply_column, disable_column = st.columns(3)
    if preview_column.button("Preview pedestal proposal", key="background-preview"):
        if aligned_path is None:
            st.error("Generate a baseline preview with aligned planes before estimating a pedestal.")
        else:
            try:
                planes = load_multiplane_records(aligned_path)
                proposal = estimate_background(planes, proposal_config)
                st.session_state["background_proposal"] = {
                    "branch": branch,
                    "aligned_path": str(aligned_path),
                    "config": proposal_config,
                    "proposal": proposal,
                }
            except (OSError, ValueError, BackgroundSamplingError) as exc:
                st.session_state.pop("background_proposal", None)
                st.error(f"Background proposal is unsupported: {exc}")

    context = st.session_state.get("background_proposal")
    proposal = None
    if (
        isinstance(context, dict)
        and context.get("branch") == branch
        and aligned_path is not None
        and context.get("aligned_path") == str(aligned_path)
        and context.get("config") == proposal_config
    ):
        proposal = context.get("proposal")
    if proposal is not None:
        st.image(background_overlay_array(proposal), caption="Background region and common support")
        st.dataframe(pd.DataFrame([
            {"plane": plane_id, **record.model_dump(mode="json")}
            for plane_id, record in proposal.resolved_planes.items()
        ]), use_container_width=True)
        try:
            planes = load_multiplane_records(aligned_path)
            applied_config = BackgroundConfig.model_validate({
                **proposal_config.model_dump(mode="json"),
                "resolved_branches": {
                    branch: {
                        key: value.model_dump(mode="json", exclude_none=True)
                        for key, value in proposal.resolved_planes.items()
                    }
                },
            })
            candidate = render_aligned_planes(
                planes,
                MappingConfig.model_validate(document(card.mapping)),
                ToneConfig.model_validate(document(card.tone)),
                bit_depth=16,
                background=applied_config,
                coverage=CoverageConfig.model_validate(
                    document(card.coverage) if card.coverage is not None else {}
                ),
            ).rgb
            st.image(
                np.clip(candidate / 257.0, 0, 255).astype(np.uint8),
                caption="Candidate after pedestal correction",
            )
        except (OSError, ValueError) as exc:
            st.warning(f"Candidate rendering is unavailable: {exc}")
        if apply_column.button("Apply pedestal proposal", key="background-apply"):
            applied = {
                **proposal_config.model_dump(mode="json"),
                "resolved_branches": {
                    **current.get("resolved_branches", {}),
                    branch: {
                        key: value.model_dump(mode="json", exclude_none=True)
                        for key, value in proposal.resolved_planes.items()
                    },
                },
            }
            st.session_state["active_card"] = edit_scene(card, {"background": applied})
            st.success("Pedestal proposal applied. Prior renders are now stale until regenerated.")
    else:
        apply_column.button("Apply pedestal proposal", key="background-apply", disabled=True)

    if disable_column.button("Disable background correction", key="background-disable"):
        st.session_state.pop("background_proposal", None)
        st.session_state["active_card"] = edit_scene(card, {"background": {
            "mode": "off",
            "black_reference_policy": "legacy_percentile",
            "inclusion_regions": [],
            "exclusion_regions": [],
            "estimator": BackgroundEstimatorConfig().model_dump(mode="json"),
            "resolved_branches": {},
        }})
        st.success("Background correction disabled. Prior applied background settings were cleared.")


def _latest_aligned_path(
    card: SceneCard, card_path: Path | None, branch: str,
) -> Path | None:
    if card_path is None:
        return None
    assets = card.assets or {}
    for render in reversed(card.renders or []):
        if render.branch != branch:
            continue
        for asset_id in render.aligned_plane_asset_ids or []:
            asset = assets.get(asset_id)
            if asset is None or asset.kind != "aligned_planes" or asset.path is None:
                continue
            path = asset_path(card_path, asset)
            if path.is_file():
                return path
    return None


def _render_tone(card: SceneCard, card_path: Path | None, branch: str) -> None:
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
    application = st.selectbox(
        "Tone application",
        ["per_channel", "shared_intensity"],
        index=0 if tone.get("application", "per_channel") == "per_channel" else 1,
        key="render-tone-application",
    )
    tone["application"] = application
    if application == "shared_intensity":
        shared = dict(tone.get("shared_stretch") or {"kind": "asinh", "parameter": 4.0})
        shared = _render_stretch_controls("Shared stretch", shared, "render-shared-stretch")
        tone["shared_stretch"] = shared
        resolution = tone.get("auto_stretch")
        if resolution is not None and (
            shared.get("kind") != "asinh"
            or shared.get("parameter") != resolution.get("resolved_parameter")
        ):
            tone.pop("auto_stretch", None)
        tone["gamut_policy"] = st.selectbox(
            "Shared-tone gamut handling", ["clip", "rescale"],
            index=0 if tone.get("gamut_policy", "clip") == "clip" else 1,
            key="render-gamut-policy",
        )
    else:
        tone.pop("shared_stretch", None)
        tone.pop("auto_stretch", None)
        for channel in ("red", "green", "blue"):
            tone["stretch"][channel] = _render_stretch_controls(
                f"{channel.title()} stretch", dict(tone["stretch"][channel]),
                f"render-{channel}-stretch",
            )
    if tone != document(card.tone):
        try:
            st.session_state["active_card"] = edit_scene(card, {"tone": tone})
            card = st.session_state["active_card"]
        except ValueError as exc:
            st.error(str(exc))
    if st.button("Use single main stretch", key="tone-single-main-stretch"):
        mapping, shared_tone = _single_main_stretch(document(card.mapping), document(card.tone))
        st.session_state["active_card"] = edit_scene(
            card, {"mapping": mapping, "tone": shared_tone}
        )
        st.success("Per-plane stretches set to linear and shared-intensity tone selected.")
        return
    _render_auto_stretch(card, card_path, branch)


def _render_stretch_controls(label: str, current: dict[str, Any], key: str) -> dict[str, Any]:
    methods = ["linear", "asinh", "gamma", "ghs"]
    kind = st.selectbox(
        f"{label} method", methods,
        index=methods.index(current.get("kind", "asinh")), key=f"{key}-kind",
    )
    if kind == "linear":
        return {"kind": "linear"}
    if kind in ("asinh", "gamma"):
        return {
            "kind": kind,
            "parameter": float(st.number_input(
                f"{label} parameter", min_value=0.000001,
                value=float(current.get("parameter", 4.0 if kind == "asinh" else 1.0)),
                key=f"{key}-parameter",
            )),
        }
    stretch_factor = float(st.number_input(
        f"{label} ln(D+1)", min_value=0.0, max_value=20.0,
        value=float(current.get("stretch_factor", 1.0)), key=f"{key}-factor",
    ))
    local_intensity = float(st.number_input(
        f"{label} local intensity", min_value=-5.0, max_value=15.0,
        value=float(current.get("local_intensity", 0.0)), key=f"{key}-local",
    ))
    symmetry = float(st.number_input(
        f"{label} symmetry point", min_value=0.0, max_value=1.0,
        value=float(current.get("symmetry_point", 0.1)), key=f"{key}-symmetry",
    ))
    shadow = float(st.number_input(
        f"{label} protect shadows", min_value=0.0, max_value=1.0,
        value=float(current.get("shadow_protection", 0.0)), key=f"{key}-shadow",
    ))
    highlight = float(st.number_input(
        f"{label} protect highlights", min_value=0.0, max_value=1.0,
        value=float(current.get("highlight_protection", 1.0)), key=f"{key}-highlight",
    ))
    return {
        "kind": "ghs", "stretch_factor": stretch_factor,
        "local_intensity": local_intensity, "symmetry_point": symmetry,
        "shadow_protection": shadow, "highlight_protection": highlight,
    }


def _single_main_stretch(
    mapping: dict[str, Any], tone: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_mapping = {**mapping}
    defaults = dict(updated_mapping.get("defaults") or {})
    normalization = dict(defaults.get("normalization") or {})
    normalization.update({"stretch": "linear", "stretch_parameter": 1.0})
    defaults["normalization"] = normalization
    updated_mapping["defaults"] = defaults
    updated_planes = []
    for entry in updated_mapping.get("planes", []):
        item = dict(entry)
        if item.get("normalization") is not None:
            item["normalization"] = {
                **item["normalization"], "stretch": "linear", "stretch_parameter": 1.0,
            }
        updated_planes.append(item)
    updated_mapping["planes"] = updated_planes
    updated_tone = {
        **tone,
        "application": "shared_intensity",
        "shared_stretch": tone.get("shared_stretch") or {"kind": "asinh", "parameter": 4.0},
        "gamut_policy": tone.get("gamut_policy", "clip"),
    }
    updated_tone.pop("auto_stretch", None)
    return updated_mapping, updated_tone


def _render_auto_stretch(card: SceneCard, card_path: Path | None, branch: str) -> None:
    aligned_path = _latest_aligned_path(card, card_path, branch)
    action = "Recompute auto-stretch proposal" if card.tone.auto_stretch else "Preview auto-stretch proposal"
    preview, apply_column = st.columns(2)
    if preview.button(action, key="auto-stretch-preview"):
        if aligned_path is None:
            st.error("Generate a baseline preview with aligned planes before auto-stretch.")
        else:
            try:
                planes = load_multiplane_records(aligned_path)
                background = BackgroundConfig.model_validate(
                    document(card.background) if card.background is not None else {}
                )
                if not background.inclusion_regions:
                    raise ValueError("auto-stretch requires persisted background regions")
                _, sample_mask, _ = background_masks(planes, background)
                coverage = CoverageConfig.model_validate(
                    document(card.coverage) if card.coverage is not None else {}
                )
                linear_tone_data = {
                    **document(card.tone), "application": "shared_intensity",
                    "shared_stretch": {"kind": "linear"}, "saturation": 1.0,
                }
                linear_tone_data.pop("auto_stretch", None)
                linear_tone = ToneConfig.model_validate(linear_tone_data)
                linear = render_aligned_planes(
                    planes, MappingConfig.model_validate(document(card.mapping)), linear_tone,
                    bit_depth=16, background=background, coverage=coverage,
                )
                x0, y0, x1, y1 = linear.coverage.crop_bounds_xyxy
                cropped_mask = sample_mask[y0:y1, x0:x1]
                reference = propose_auto_stretch(
                    linear.rgb / 65535.0, cropped_mask,
                    reference_id=background_selection_key(planes, background),
                    branch=branch, grid_id=str(planes[0].grid_id),
                    source_ids=list(dict.fromkeys(
                        source for plane in planes for source in plane.source_ids
                    )),
                    minimum_samples=background.estimator.minimum_samples,
                )
                proposed_data = {
                    **document(card.tone), "application": "shared_intensity",
                    "shared_stretch": {
                        "kind": "asinh", "parameter": reference.resolved_parameter,
                    },
                    "auto_stretch": reference.model_dump(mode="json"),
                }
                proposed = ToneConfig.model_validate(proposed_data)
                candidate = render_aligned_planes(
                    planes, MappingConfig.model_validate(document(card.mapping)), proposed,
                    bit_depth=16, background=background, coverage=coverage,
                )
                st.session_state["auto_stretch_proposal"] = {
                    "branch": branch, "aligned_path": str(aligned_path),
                    "tone": proposed, "reference": reference, "image": candidate.rgb,
                }
            except (OSError, ValueError, BackgroundSamplingError) as exc:
                st.session_state.pop("auto_stretch_proposal", None)
                st.error(f"Auto-stretch proposal is unavailable: {exc}")
    context = st.session_state.get("auto_stretch_proposal")
    valid = (
        isinstance(context, dict) and context.get("branch") == branch
        and aligned_path is not None and context.get("aligned_path") == str(aligned_path)
    )
    if valid:
        st.json(context["reference"].model_dump(mode="json"))
        st.image(
            np.clip(context["image"] / 257.0, 0, 255).astype(np.uint8),
            caption="Auto-stretch candidate",
        )
        if apply_column.button("Apply auto-stretch proposal", key="auto-stretch-apply"):
            st.session_state["active_card"] = edit_scene(
                card, {"tone": context["tone"].model_dump(mode="json")}
            )
            st.success("Auto-stretch proposal applied. Prior renders are now stale.")
    else:
        apply_column.button(
            "Apply auto-stretch proposal", key="auto-stretch-apply", disabled=True,
        )


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
                    card,
                    card_path,
                    destination,
                    output_format=output_format,
                    overwrite=overwrite,
                    branch=st.session_state.get("render-branch", "original"),
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
    success = st.session_state.pop("project_delete_success", None)
    if success:
        st.success(success)
    if _render_project_delete_confirmation(settings, library.saved_scenes):
        return
    if _render_example_overwrite_confirmation(settings):
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


def _same_path(left: str | Path | None, right: str | Path | None) -> bool:
    return left is not None and right is not None and Path(left).resolve() == Path(right).resolve()


def _project_delete_blocked(path: Path) -> bool:
    job: RenderJob | None = st.session_state.get("render_job")
    return bool(
        job is not None
        and _same_path(st.session_state.get("active_path"), path)
        and job.snapshot().phase is OperationPhase.RUNNING
    )


def _render_project_delete_confirmation(
    settings: ApplicationSettings, entries: tuple[LibraryEntry, ...]
) -> bool:
    pending = st.session_state.get("pending_project_delete")
    if pending is None:
        return False
    entry = next((item for item in entries if _same_path(item.path, pending)), None)
    if entry is None or entry.card is None:
        st.session_state.pop("pending_project_delete", None)
        st.error("The selected project no longer exists or is not a valid saved scene.")
        return True
    asset_root = associated_asset_root(entry.path)
    st.warning(f'Delete project "{entry.card.title}"?')
    st.write(f"Scene card: {entry.path}")
    st.write(
        f"Associated asset folder: {asset_root}"
        if asset_root.exists() else "Associated asset folder: none"
    )
    st.caption("Deletion moves these items into .galaxy-trash for manual recovery.")
    blocked = _project_delete_blocked(entry.path)
    if blocked:
        st.error("This project cannot be deleted while its render is running.")
    confirm, cancel = st.columns(2)
    if confirm.button("Delete project", key="confirm-project-delete", disabled=blocked):
        try:
            deleted = delete_library_scene(entry, settings.scene_directory)
            was_active = _same_path(st.session_state.get("active_path"), entry.path)
            st.session_state.pop("pending_project_delete", None)
            if was_active:
                _close_active_scene()
                st.session_state["screen"] = Screen.LIBRARY.value
            st.session_state["operation_phase"] = OperationPhase.SUCCEEDED.value
            st.session_state["operation_message"] = f'Deleted project "{entry.card.title}"'
            st.session_state["project_delete_success"] = (
                f'Deleted project "{entry.card.title}". Recovery files: '
                f"{deleted.recovery_directory}"
            )
            st.rerun()
        except (OSError, ValueError) as exc:
            st.session_state["operation_phase"] = OperationPhase.FAILED.value
            st.session_state["operation_message"] = str(exc)
            st.error(f"Delete failed: {exc}")
    if cancel.button("Cancel", key="cancel-project-delete"):
        st.session_state.pop("pending_project_delete", None)
        st.rerun()
    return True


def _render_example_overwrite_confirmation(settings: ApplicationSettings) -> bool:
    source_text = st.session_state.get("pending_example_overwrite")
    if source_text is None:
        return False
    source = Path(source_text)
    destination = example_user_path(source, settings.scene_directory)
    st.warning(f"Replace the user scene JSON at {destination}?")
    st.write("The matching binary asset folder will be retained unchanged.")
    confirm, cancel = st.columns(2)
    if confirm.button("Overwrite user scene JSON", key="confirm-example-overwrite"):
        try:
            copied, path = materialize_example(source, settings.scene_directory, overwrite=True)
            st.session_state.pop("pending_example_overwrite", None)
            _request_scene_replacement(copied, path, saved=True)
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(f"Example overwrite failed: {exc}")
    if cancel.button("Cancel overwrite", key="cancel-example-overwrite"):
        st.session_state.pop("pending_example_overwrite", None)
        st.rerun()
    return True


def _render_library_entries(
    entries: tuple[LibraryEntry, ...], settings: ApplicationSettings, group: str
) -> None:
    for index, entry in enumerate(entries):
        if entry.card is None:
            st.error(f"{entry.path.name}: invalid scene card - {entry.error}")
            continue
        columns = st.columns([1, 3, 1, 1, 1])
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
            try:
                if entry.origin is LibraryOrigin.BUNDLED_EXAMPLE:
                    card, path = open_example_user_copy(entry.path, settings.scene_directory)
                    _request_scene_replacement(card, path, saved=True)
                else:
                    _request_scene_replacement(entry.card, entry.path, saved=True)
                st.rerun()
            except (OSError, ValueError) as exc:
                st.error(f"Open failed: {exc}")
        if columns[3].button("Duplicate", key=f"library-copy-{group}-{index}"):
            try:
                if (
                    entry.origin is LibraryOrigin.BUNDLED_EXAMPLE
                    and example_user_path(entry.path, settings.scene_directory).exists()
                ):
                    st.session_state["pending_example_overwrite"] = str(entry.path)
                    st.rerun()
                copied, _ = duplicate_library_scene(entry, settings.scene_directory)
                path = (
                    example_user_path(entry.path, settings.scene_directory)
                    if entry.origin is LibraryOrigin.BUNDLED_EXAMPLE else None
                )
                _request_scene_replacement(
                    copied, path, saved=True
                )
                st.rerun()
            except (OSError, ValueError) as exc:
                st.error(f"Duplicate failed: {exc}")
        if entry.origin is LibraryOrigin.USER_SCENE:
            blocked = _project_delete_blocked(entry.path)
            if columns[4].button(
                "Delete", key=f"library-delete-{group}-{index}", disabled=blocked,
                help="A running render must finish or be cancelled before deletion." if blocked else None,
            ):
                st.session_state["pending_project_delete"] = str(entry.path)
                st.rerun()


if __name__ == "__main__":  # Streamlit executes this file as the application script.
    main()

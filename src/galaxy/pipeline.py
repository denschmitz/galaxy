from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Callable

import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS

from galaxy.cache import ensure_directory, write_manifest
from galaxy.artifact_paths import branch_artifact_paths, existing_branch_artifact_paths
from galaxy.background import (
    BackgroundProposal,
    background_masks,
    write_background_diagnostics,
    write_background_overlay,
)
from galaxy.checkpoints import (
    build_producer_inputs,
    checkpoint_stage_record,
    load_validated_checkpoint,
    read_checkpoint_manifest,
    write_checkpoint_manifest,
)
from galaxy.processing_config import GalaxyConfig
from galaxy.export import export_footprint_overlay, export_png, export_tiff
from galaxy.bridge import NativePresentation, prepare_native_presentation
from galaxy.fitsio import FITSPlane, load_fits_plane
from galaxy.logging_utils import configure_logging, emit_log
from galaxy.mast import build_candidate_manifest, discover_candidates, download_selected, selection_summary
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_records
from galaxy.provenance import build_provenance, write_provenance
from galaxy.psf import build_deconvolved_plane_artifacts
from galaxy.reprojection import (
    MEMORY_WARNING_FRACTION,
    REPROJECT_METHOD_ADAPTIVE_FLUX,
    REPROJECT_METHOD_INTERPOLATION,
    ReprojectedPlane,
    build_output_wcs,
    estimate_workspace_peak_bytes,
    get_system_memory_bytes,
    reproject_all,
    save_reprojected_plane,
)
from galaxy.rendering import render_aligned_planes
from galaxy.selection import CandidateManifest, SelectionInputs, write_candidate_manifest
from galaxy.scene_models import SceneCard
from galaxy.scene_readiness import readiness
from galaxy.targeting import ResolvedTarget, region_to_mast_shape, resolve_target
from galaxy.viewport_framing import fit_planes


logger = logging.getLogger(__name__)


class PipelineCancelled(RuntimeError):
    """Raised only at a processing boundary after cancellation is requested."""


def _cancellation_checkpoint(cancel_requested: Callable[[], bool] | None, stage: str) -> None:
    if cancel_requested is not None and cancel_requested():
        raise PipelineCancelled(f"render cancelled before {stage}")


@dataclass(slots=True)
class PipelineArtifacts:
    workdir: Path
    manifest_path: Path
    planes_path: Path | None
    deconvolved_planes_path: Path | None
    checkpoint_manifest_path: Path | None
    deconvolved_checkpoint_manifest_path: Path | None
    footprint_overlay_path: Path | None
    png_path: Path | None
    deconvolved_png_path: Path | None
    tiff_path: Path | None
    deconvolved_tiff_path: Path | None
    background_diagnostics_path: Path | None
    deconvolved_background_diagnostics_path: Path | None
    background_overlay_path: Path | None
    deconvolved_background_overlay_path: Path | None
    provenance_path: Path
    config_path: Path
    inspected_plane_filters: dict[str, str]
    effective_canvas: dict[str, object] | None


@dataclass(slots=True)
class ReprojectionLoadResult:
    original_planes: list[ReprojectedPlane]
    deconvolved_planes: list[ReprojectedPlane]
    diagnostics: dict[str, object]
    output_wcs: WCS | None = None


def run_pipeline(
    config: GalaxyConfig,
    workdir: str | Path,
    mode: str = "full",
    progress: Callable[[str], None] | None = None,
    *,
    config_path: str | None = None,
    selection_manifest: CandidateManifest | None = None,
    selection_inputs: SelectionInputs | None = None,
    pinned_selection: bool = False,
    local_product_paths: dict[str, Path] | None = None,
    scene_card: SceneCard | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> PipelineArtifacts:
    output_dir = ensure_directory(workdir)
    configure_logging(
        log_path=output_dir / config.execution.log_file,
        debug_to_console=config.execution.debug_to_console,
        debug_to_file=config.execution.debug_to_file,
    )
    cache_dir = ensure_directory(output_dir / "cache")
    reprojected_dir = output_dir

    emit_log(logger, logging.INFO, f"Pipeline start: mode={mode} workdir={output_dir}", progress)
    _cancellation_checkpoint(cancel_requested, "target resolution")

    resolved_target = resolve_target(config.target) if config.target is not None else None
    shape_kind = None
    shape_kwargs = None
    if resolved_target is not None:
        shape_kind, shape_kwargs = region_to_mast_shape(config.target.region, resolved_target.coord)
        resolved_center = resolved_target.coord
    elif config.canvas.center.mode == "explicit":
        resolved_center = SkyCoord(config.canvas.center.ra_deg * u.deg, config.canvas.center.dec_deg * u.deg)
        resolved_target = ResolvedTarget(coord=resolved_center.icrs, source="explicit-canvas", region={})
    else:
        resolved_center = None

    candidate_manifest: CandidateManifest | None = None
    execution_source = (
        "pinned_scene_card" if pinned_selection
        else "saved_candidate_manifest" if selection_manifest is not None
        else "raw_config_discovery"
    )
    manifest: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    cached_paths: list[Path] = sorted(cache_dir.glob("*.fits*"))
    if mode == "compose-only" and local_product_paths:
        cached_paths = sorted(Path(path) for path in local_product_paths.values())

    if mode in {"full", "download-only", "reproject-only"}:
        _cancellation_checkpoint(cancel_requested, "discovery and download")
        if mode in {"full", "download-only"} or not cached_paths:
            if selection_manifest is None:
                if shape_kind is None or shape_kwargs is None:
                    logger.error("Pipeline cannot perform discovery without a target-defined search geometry")
                    raise RuntimeError("discovery execution requires a target-defined search geometry")
                candidates = discover_candidates(shape_kind, shape_kwargs, config.search, progress=progress)
                candidate_manifest = build_candidate_manifest(
                    candidates,
                    config.search,
                    config_path=config_path,
                    selection_inputs=selection_inputs,
                )
            elif pinned_selection:
                emit_log(logger, logging.INFO, "Using exact product pins from scene card", progress)
                candidate_manifest = selection_manifest
            else:
                emit_log(logger, logging.INFO, "Loaded candidate manifest for execution", progress)
                merged_inputs = _merge_selection_inputs(selection_manifest.selection_inputs, selection_inputs)
                candidate_manifest = build_candidate_manifest(
                    selection_manifest.candidates,
                    config.search,
                    config_path=selection_manifest.config_path or config_path,
                    selection_inputs=merged_inputs,
                )

            write_candidate_manifest(candidate_manifest, output_dir / "candidates.json")
            emit_log(logger, logging.INFO, f"Candidate manifest write location: {output_dir / 'candidates.json'}", progress)
            summary = selection_summary(candidate_manifest.candidates)
            emit_log(logger, logging.INFO, f"Automatic selection result count: {summary['auto_selected_count']}", progress)
            emit_log(logger, logging.INFO, f"Final explicit selection result count: {summary['selected_count']}", progress)
            if summary["filters"]:
                emit_log(logger, logging.INFO, f"Available filters: {', '.join(summary['filters'])}", progress)
            if summary["instruments"]:
                emit_log(logger, logging.INFO, f"Available instruments: {', '.join(summary['instruments'])}", progress)

            selected_candidates = [candidate for candidate in candidate_manifest.candidates if candidate.selected]
            if not selected_candidates:
                logger.error("Archive discovery produced no selected candidates")
                raise RuntimeError(
                    "archive discovery produced no selected candidates; adjust the selection policy, explicit overrides, or base search filters"
                )
            manifest = _local_product_manifest(candidate_manifest, local_product_paths or {})
            local_ids = {str(entry["candidate_id"]) for entry in manifest}
            remote_candidates = [
                candidate for candidate in candidate_manifest.candidates
                if candidate.selected and candidate.candidate_id not in local_ids
            ]
            downloaded, skipped = (
                download_selected(remote_candidates, cache_dir, progress=progress)
                if remote_candidates else ([], [])
            )
            manifest.extend(downloaded)
            _cancellation_checkpoint(cancel_requested, "manifest publication")
            write_manifest(manifest, output_dir / "manifest.json")
            cached_paths = [Path(entry["local_path"]) for entry in manifest]
            emit_log(logger, logging.INFO, f"Downloaded or reused {len(cached_paths)} FITS files", progress)
            if not cached_paths:
                first_reason = skipped[0]["reason"] if skipped else "none recorded"
                logger.error(
                    "All selected candidate downloads failed or were skipped (selected=%s skipped=%s first_failure=%s)",
                    len(selected_candidates),
                    len(skipped),
                    first_reason,
                )
                raise RuntimeError(
                    f"all selected candidate downloads failed or were skipped (selected={len(selected_candidates)}, skipped={len(skipped)}). "
                    f"First failure: {first_reason}"
                )

    if mode == "download-only":
        _cancellation_checkpoint(cancel_requested, "download provenance")
        provenance = build_provenance(
            config,
            resolved_target,
            manifest,
            skipped,
            [],
            {},
            candidate_manifest,
            execution_source,
        )
        write_provenance(provenance, output_dir / "provenance.json")
        emit_log(logger, logging.INFO, "Pipeline finished in download-only mode", progress)
        return _finalize_artifacts(output_dir, Path(config_path) if config_path else None)

    if resolved_center is None:
        logger.error("Pipeline cannot continue without target coordinates for reprojection")
        raise RuntimeError("reprojection and composition require a target-defined scene")

    source_ids_by_path = _source_ids_by_path(manifest, local_product_paths or {})

    _cancellation_checkpoint(cancel_requested, "reprojection")
    reprojected_result = _load_or_build_reprojected(
        config,
        resolved_center,
        cached_paths,
        cache_dir,
        output_dir,
        reprojected_dir,
        mode,
        progress,
        scene_card=scene_card,
        source_ids_by_path=source_ids_by_path,
    )
    original_reprojected = reprojected_result.original_planes
    deconvolved_reprojected = reprojected_result.deconvolved_planes
    _cancellation_checkpoint(cancel_requested, "aligned-plane export")
    if not original_reprojected:
        diagnostics = reprojected_result.diagnostics
        logger.error(
            "No usable planes were available for reprojection or composition (cached_fits=%s loaded=%s filter_skipped=%s load_failed=%s first_failure=%s)",
            diagnostics["cached_fits"],
            diagnostics["loaded"],
            diagnostics["filter_skipped"],
            diagnostics["load_failed"],
            diagnostics["first_failure"] or "none recorded",
        )
        raise RuntimeError(
            "no usable planes were available for reprojection or composition "
            f"(cached_fits={diagnostics['cached_fits']}, loaded={diagnostics['loaded']}, "
            f"filter_skipped={diagnostics['filter_skipped']}, load_failed={diagnostics['load_failed']}). "
            f"First failure: {diagnostics['first_failure'] or 'none recorded'}"
        )

    _validate_selected_plane_coverage(original_reprojected)

    original_records = build_plane_records(
        original_reprojected, set(config.planes.disabled_plane_ids), artifact_branch="original"
    )
    original_paths = (
        existing_branch_artifact_paths(output_dir, "original")
        if mode == "compose-only" else branch_artifact_paths(output_dir, "original")
    )
    if original_paths is None:
        raise RuntimeError(
            "compose-only requires an aligned checkpoint; run full or reprojection-only processing"
        )
    original_planes_path: Path | None = original_paths.aligned_planes
    original_checkpoint_path: Path | None = original_paths.checkpoint_manifest
    if mode != "compose-only":
        original_records, original_planes_path = _export_branch_planes(
            original_reprojected,
            config,
            original_planes_path,
            output_wcs=reprojected_result.output_wcs,
            artifact_branch="original",
        )
        original_checkpoint_path = None
    if mode != "compose-only" and original_planes_path is not None:
        _cancellation_checkpoint(cancel_requested, "original checkpoint publication")
        original_checkpoint_path = write_checkpoint_manifest(
            original_reprojected,
            original_planes_path,
            build_producer_inputs(
                config,
                cached_paths,
                "original",
                resolved_center_deg=(float(resolved_center.ra.deg), float(resolved_center.dec.deg)),
                source_ids_by_path=source_ids_by_path,
            ),
            "original",
            destination=original_paths.checkpoint_manifest,
            resolved_settings=_reprojection_settings(reprojected_result.diagnostics),
        )
    deconvolved_records: list = []
    deconvolved_planes_path: Path | None = None
    deconvolved_checkpoint_path: Path | None = None
    if deconvolved_reprojected:
        deconvolved_records = build_plane_records(
            deconvolved_reprojected,
            set(config.planes.disabled_plane_ids),
            artifact_branch="deconvolved",
        )
        deconvolved_paths = (
            existing_branch_artifact_paths(output_dir, "deconvolved")
            if mode == "compose-only" else branch_artifact_paths(output_dir, "deconvolved")
        )
        if deconvolved_paths is None:
            raise RuntimeError(
                "compose-only requires the requested deconvolved checkpoint; run full processing"
            )
        deconvolved_planes_path = deconvolved_paths.aligned_planes
        deconvolved_checkpoint_path = deconvolved_paths.checkpoint_manifest
        if mode != "compose-only":
            deconvolved_records, deconvolved_planes_path = _export_branch_planes(
                deconvolved_reprojected,
                config,
                deconvolved_planes_path,
                output_wcs=reprojected_result.output_wcs,
                artifact_branch="deconvolved",
            )
            deconvolved_checkpoint_path = None
        if mode != "compose-only" and deconvolved_planes_path is not None:
            _cancellation_checkpoint(cancel_requested, "deconvolved checkpoint publication")
            deconvolved_checkpoint_path = write_checkpoint_manifest(
                deconvolved_reprojected,
                deconvolved_planes_path,
                build_producer_inputs(
                    config,
                    cached_paths,
                    "deconvolved",
                    resolved_center_deg=(float(resolved_center.ra.deg), float(resolved_center.dec.deg)),
                    source_ids_by_path=source_ids_by_path,
                ),
                "deconvolved",
                destination=deconvolved_paths.checkpoint_manifest,
                resolved_settings=_reprojection_settings(reprojected_result.diagnostics),
            )

    footprint_overlay_path = _export_footprint_overlay(original_reprojected, output_dir / "footprints.png")
    _cancellation_checkpoint(cancel_requested, "composition")

    if mode == "reproject-only":
        provenance = build_provenance(
            config,
            resolved_target,
            manifest,
            skipped,
            original_records + deconvolved_records,
            _reprojection_settings(reprojected_result.diagnostics),
            candidate_manifest,
            execution_source,
            stage_records=_checkpoint_stage_records(
                original_checkpoint_path, deconvolved_checkpoint_path
            ),
        )
        write_provenance(provenance, output_dir / "provenance.json")
        emit_log(logger, logging.INFO, "Pipeline finished in reproject-only mode", progress)
        return _finalize_artifacts(output_dir, Path(config_path) if config_path else None)

    (
        png_path, tiff_path, display_warnings, original_background_stage,
        original_coverage_stage,
        background_diagnostics_path, background_overlay_path,
    ) = _compose_and_export_branch(
        original_reprojected,
        original_records,
        config,
        original_paths.composite_png,
        original_paths.composite_tiff,
    )
    deconvolved_png_path: Path | None = None
    deconvolved_tiff_path: Path | None = None
    deconvolved_background_diagnostics_path: Path | None = None
    deconvolved_background_overlay_path: Path | None = None
    deconvolved_background_stage: dict[str, object] | None = None
    deconvolved_coverage_stage: dict[str, object] | None = None
    if deconvolved_reprojected:
        (
            deconvolved_png_path, deconvolved_tiff_path, deconvolved_warnings,
            deconvolved_background_stage, deconvolved_coverage_stage,
            deconvolved_background_diagnostics_path,
            deconvolved_background_overlay_path,
        ) = _compose_and_export_branch(
            deconvolved_reprojected,
            deconvolved_records,
            config,
            deconvolved_paths.composite_png,
            deconvolved_paths.composite_tiff,
        )
        display_warnings.extend(deconvolved_warnings)

    _cancellation_checkpoint(cancel_requested, "provenance and history commit")

    provenance = build_provenance(
        config,
        resolved_target,
        manifest,
        skipped,
        original_records + deconvolved_records,
        _reprojection_settings(reprojected_result.diagnostics),
        candidate_manifest,
        execution_source,
        display_warnings=sorted(set(display_warnings)),
        stage_records=(
            _checkpoint_stage_records(original_checkpoint_path, deconvolved_checkpoint_path)
            + [record for record in (
                original_background_stage, original_coverage_stage,
                deconvolved_background_stage, deconvolved_coverage_stage,
            )
               if record is not None]
        ),
    )
    write_provenance(provenance, output_dir / "provenance.json")
    emit_log(logger, logging.INFO, "Pipeline finished successfully", progress)
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=original_planes_path,
        deconvolved_planes_path=deconvolved_planes_path,
        checkpoint_manifest_path=original_checkpoint_path,
        deconvolved_checkpoint_manifest_path=deconvolved_checkpoint_path,
        footprint_overlay_path=footprint_overlay_path,
        png_path=png_path,
        deconvolved_png_path=deconvolved_png_path,
        tiff_path=tiff_path,
        deconvolved_tiff_path=deconvolved_tiff_path,
        background_diagnostics_path=background_diagnostics_path,
        deconvolved_background_diagnostics_path=deconvolved_background_diagnostics_path,
        background_overlay_path=background_overlay_path,
        deconvolved_background_overlay_path=deconvolved_background_overlay_path,
        provenance_path=output_dir / "provenance.json",
        config_path=Path(config_path) if config_path else output_dir / "scene-card-input.json",
        inspected_plane_filters={
            plane.plane_id: str(plane.metadata.get("filter") or "")
            for plane in original_reprojected
        },
        effective_canvas=(
            {**config.canvas.model_dump(mode="json", exclude_none=True),
             "frame_origin": "selected_footprints"}
            if reprojected_result.diagnostics.get("auto_fitted") else None
        ),
    )


def _validate_selected_plane_coverage(planes: list[ReprojectedPlane]) -> None:
    zero_coverage = [
        plane.plane_id
        for plane in planes
        if not np.any(np.asarray(plane.footprint) > 0)
    ]
    if zero_coverage:
        identifiers = ", ".join(sorted(zero_coverage))
        raise RuntimeError(
            "selected FITS products have zero footprint coverage on the configured canvas: "
            f"{identifiers}"
        )


def _load_or_build_reprojected(
    config: GalaxyConfig,
    resolved_center,
    cached_paths: list[Path],
    cache_dir: Path,
    output_dir: Path,
    reprojected_dir: Path,
    mode: str,
    progress: Callable[[str], None] | None,
    *,
    scene_card: SceneCard | None = None,
    source_ids_by_path: dict[Path, str] | None = None,
) -> ReprojectionLoadResult:
    original_paths = existing_branch_artifact_paths(output_dir, "original")
    deconvolved_paths = existing_branch_artifact_paths(output_dir, "deconvolved")
    if mode == "compose-only":
        if original_paths is None:
            raise RuntimeError(
                "compose-only requires an aligned checkpoint; run full or reprojection-only processing"
            )
        emit_log(logger, logging.INFO, "Compose-only mode validating aligned checkpoints", progress)
        center = (float(resolved_center.ra.deg), float(resolved_center.dec.deg))
        original_inputs = build_producer_inputs(
            config,
            cached_paths,
            "original",
            resolved_center_deg=center,
            source_ids_by_path=source_ids_by_path,
        )
        _, original_planes = load_validated_checkpoint(
            original_paths.aligned_planes,
            original_paths.checkpoint_manifest,
            original_inputs,
            "original",
        )
        deconvolved_planes: list[ReprojectedPlane] = []
        if config.psf.enabled:
            if deconvolved_paths is None:
                raise RuntimeError(
                    "compose-only requires the requested deconvolved checkpoint; run full processing"
                )
            deconvolved_inputs = build_producer_inputs(
                config,
                cached_paths,
                "deconvolved",
                resolved_center_deg=center,
                source_ids_by_path=source_ids_by_path,
            )
            _, deconvolved_planes = load_validated_checkpoint(
                deconvolved_paths.aligned_planes,
                deconvolved_paths.checkpoint_manifest,
                deconvolved_inputs,
                "deconvolved",
            )
        _validate_inspected_scene(scene_card, original_planes, require_deconvolved=bool(deconvolved_planes))
        return ReprojectionLoadResult(
            original_planes=original_planes,
            deconvolved_planes=deconvolved_planes,
            diagnostics={
                "mode": "compose_only_export",
                "reference_plane_id": None,
                "expand_fraction": 0.10,
                "pixel_scale_arcsec": None,
                "width": original_planes[0].data.shape[1] if original_planes else 0,
                "height": original_planes[0].data.shape[0] if original_planes else 0,
                "cached_fits": 0,
                "loaded": len(original_planes),
                "filter_skipped": 0,
                "load_failed": 0,
                "first_failure": None,
                "deconvolved_loaded": len(deconvolved_planes),
            },
            output_wcs=None,
        )

    fits_planes: list[FITSPlane] = []
    original_presentations: list[NativePresentation] = []
    filter_skipped = 0
    load_failed = 0
    first_failure: str | None = None

    emit_log(logger, logging.INFO, f"Loading cached FITS planes from {len(cached_paths)} files", progress)

    for source_path in cached_paths:
        try:
            plane = load_fits_plane(source_path)
            authoritative_source_id = (source_ids_by_path or {}).get(source_path.resolve())
            if authoritative_source_id is not None:
                plane.source_ids = (authoritative_source_id,)
            plane.metadata.setdefault("artifact_branch", "original")
            plane_filter = str(plane.metadata.get("filter") or "")
            if config.planes.enabled_filters and plane_filter not in config.planes.enabled_filters:
                filter_skipped += 1
                emit_log(logger, logging.WARNING, f"Skipping {source_path.name}: filter '{plane_filter or 'unknown'}' not in enabled_filters", progress)
                continue
            fits_planes.append(plane)
        except Exception as exc:
            load_failed += 1
            if first_failure is None:
                first_failure = f"{source_path.name}: {exc}"
            emit_log(logger, logging.WARNING, f"Skipping {source_path.name}: {exc}", progress)
            if config.execution.fail_fast:
                raise
            continue
        # Keep preparation outside the FITS-load skip handler: numerical failures
        # must abort rather than silently falling back to strict processing.
        original_presentations.append(prepare_native_presentation(plane, enabled=config.bridge.enabled))

    diagnostics = {
        "cached_fits": len(cached_paths),
        "loaded": len(fits_planes),
        "filter_skipped": filter_skipped,
        "load_failed": load_failed,
        "first_failure": first_failure,
    }

    emit_log(
        logger,
        logging.INFO,
        f"Loaded {len(fits_planes)} usable FITS planes (filter_skipped={filter_skipped}, load_failed={load_failed})",
        progress,
    )

    if not fits_planes:
        return ReprojectionLoadResult(original_planes=[], deconvolved_planes=[], diagnostics=diagnostics)

    _validate_inspected_scene(scene_card, fits_planes, require_deconvolved=config.psf.enabled)

    if scene_card is not None and scene_card.canvas is not None \
            and scene_card.canvas.frame_origin == "search_region":
        products = {
            (product.filename or ""): product.product_id
            for product in (scene_card.selection.products or [])
        } if scene_card.selection else {}
        identities = [
            products.get(Path(str(plane.metadata.get("source_path", ""))).name, plane.plane_id)
            for plane in fits_planes
        ]
        fitted = fit_planes(fits_planes, identities)
        if fitted.warnings:
            raise RuntimeError(
                "selected FITS footprints require confirmation before an extreme frame is applied: "
                + " ".join(fitted.warnings)
                + " Use Fit selected scans in Scene refinement to revise, apply, or keep the frame."
            )
        config.canvas = type(config.canvas).model_validate({
            key: value for key, value in fitted.canvas.items() if key != "frame_origin"
        })
        diagnostics["auto_fitted"] = True

    deconvolved_fits_planes: list[FITSPlane] = []
    if config.psf.enabled:
        emit_log(logger, logging.INFO, "Building deconvolved cache companions", progress)
        deconvolved_fits_planes = build_deconvolved_plane_artifacts(fits_planes, config.psf, cache_dir)
        diagnostics["deconvolved_loaded"] = len(deconvolved_fits_planes)
        emit_log(logger, logging.INFO, f"Built {len(deconvolved_fits_planes)} deconvolved cache companions", progress)
    else:
        diagnostics["deconvolved_loaded"] = 0

    deconvolved_presentations = [
        prepare_native_presentation(plane, enabled=config.bridge.enabled)
        for plane in deconvolved_fits_planes
    ]
    prepared = [*original_presentations, *deconvolved_presentations]
    retained_native_bytes = sum(
        item.observation.data.nbytes + item.observation.valid.nbytes + item.observation.coverage.nbytes
        + item.observation.mask.nbytes + item.values.nbytes + item.support.nbytes + item.estimate_mask.nbytes
        for item in prepared
    )
    bridge_workspace_bytes = max((item.diagnostics.estimated_peak_working_bytes for item in prepared), default=0)
    diagnostics["bridge"] = {item.observation.plane_id: item.diagnostics.record() for item in prepared}
    output_wcs, shape_out = build_output_wcs(config.canvas, resolved_center)
    reprojection_method = REPROJECT_METHOD_ADAPTIVE_FLUX if config.canvas.flux_conserving else REPROJECT_METHOD_INTERPOLATION
    reprojection_bytes_per_pixel = 16 if config.canvas.flux_conserving else 8
    canvas_diag = {
        "mode": "configured_canvas",
        "reference_plane_id": None,
        "expand_fraction": None,
        "pixel_scale_arcsec": config.canvas.pixel_scale_arcsec,
        "width": shape_out[1],
        "height": shape_out[0],
        "projection": config.canvas.projection,
        "rotation_deg": config.canvas.rotation_deg,
        "center_mode": config.canvas.center.mode,
        "center_ra_deg": output_wcs.wcs.crval[0],
        "center_dec_deg": output_wcs.wcs.crval[1],
        "flux_conserving": config.canvas.flux_conserving,
        "reprojection_method": reprojection_method,
        "reprojection_bytes_per_pixel": reprojection_bytes_per_pixel,
    }
    estimated_peak_bytes = estimate_workspace_peak_bytes(
        shape_out[0] * shape_out[1],
        len(fits_planes) + len(deconvolved_fits_planes),
        reprojection_bytes_per_pixel,
        reprojection_method,
        native_bridge_peak_bytes=retained_native_bytes + bridge_workspace_bytes,
    )
    system_memory_bytes = get_system_memory_bytes()
    canvas_diag.update(
        {
            "estimated_peak_bytes": estimated_peak_bytes,
            "system_memory_bytes": system_memory_bytes,
            "memory_warning_fraction": MEMORY_WARNING_FRACTION,
        }
    )
    diagnostics.update(canvas_diag)
    emit_log(
        logger,
        logging.INFO,
        (
            f"Reprojection parameters: canvas={shape_out[1]}x{shape_out[0]} pixel_scale_arcsec={config.canvas.pixel_scale_arcsec:.3f} "
            f"projection={config.canvas.projection} rotation_deg={config.canvas.rotation_deg:.3f} "
            f"method={reprojection_method}"
        ),
        progress,
    )
    if system_memory_bytes is not None and estimated_peak_bytes >= int(system_memory_bytes * MEMORY_WARNING_FRACTION):
        warning_message = (
            "Warning: estimated reprojection working set is at or above "
            f"{int(MEMORY_WARNING_FRACTION * 100)}% of system RAM "
            f"({estimated_peak_bytes / (1024 ** 3):.1f} GiB estimated vs "
            f"{system_memory_bytes / (1024 ** 3):.1f} GiB installed)."
        )
        emit_log(logger, logging.WARNING, warning_message, progress)

    original_reprojected = reproject_all(original_presentations, output_wcs, shape_out, config.canvas.flux_conserving, progress=progress)
    for plane in original_reprojected:
        plane.metadata.setdefault("artifact_branch", "original")
        save_reprojected_plane(plane, output_wcs, reprojected_dir / "original" / "aligned")

    deconvolved_reprojected: list[ReprojectedPlane] = []
    if deconvolved_fits_planes:
        deconvolved_reprojected = reproject_all(
            deconvolved_presentations,
            output_wcs,
            shape_out,
            config.canvas.flux_conserving,
            progress=progress,
        )
        for plane in deconvolved_reprojected:
            plane.metadata.setdefault("artifact_branch", "deconvolved")
            save_reprojected_plane(plane, output_wcs, reprojected_dir / "deconvolved" / "aligned")

    return ReprojectionLoadResult(
        original_planes=original_reprojected,
        deconvolved_planes=deconvolved_reprojected,
        diagnostics=diagnostics,
        output_wcs=output_wcs,
    )


def _export_branch_planes(
    planes: list[ReprojectedPlane],
    config: GalaxyConfig,
    output_path: Path,
    *,
    output_wcs: WCS | None,
    artifact_branch: str,
):
    records = build_plane_records(planes, set(config.planes.disabled_plane_ids), artifact_branch=artifact_branch)
    planes_path: Path | None = None
    if config.planes.export_multiplane_fits:
        planes_path = export_multiplane_fits(planes, output_path, output_wcs=output_wcs)
    return records, planes_path


def _export_footprint_overlay(planes: list[ReprojectedPlane], output_path: Path) -> Path | None:
    if not planes:
        return None
    return export_footprint_overlay([plane.footprint for plane in planes], output_path)


def _compose_and_export_branch(
    planes: list[ReprojectedPlane],
    records,
    config: GalaxyConfig,
    png_output: Path,
    tiff_output: Path,
) -> tuple[
    Path, Path, list[str], dict[str, object] | None, dict[str, object], Path | None, Path | None,
]:
    enabled_planes = {record.plane_id for record in records if record.enabled}
    rendered = render_aligned_planes(
        planes,
        config.mapping,
        config.tone,
        enabled_planes=enabled_planes,
        bit_depth=16,
        background=config.background,
        coverage=config.coverage,
    )
    result = rendered.composition
    by_id = {record.plane_id: record for record in records}
    for plane_id, diagnostic in result.plane_diagnostics.items():
        record = by_id.get(plane_id)
        if record is None:
            continue
        record.native_unit = _string_or_none(diagnostic.get("native_unit"))
        record.mask_sources = [str(item) for item in diagnostic.get("mask_sources", [])]
        record.valid_coverage_fraction = _float_or_none(diagnostic.get("valid_coverage_fraction"))
        record.normalization_mode = _string_or_none(diagnostic.get("normalization_mode"))
        record.black_percentile = _float_or_none(diagnostic.get("black_percentile"))
        record.white_percentile = _float_or_none(diagnostic.get("white_percentile"))
        record.black_point = _float_or_none(diagnostic.get("black_point"))
        record.white_point = _float_or_none(diagnostic.get("white_point"))
        record.plane_gain = _float_or_none(diagnostic.get("gain"))
        contribution = diagnostic.get("rgb_contribution_percent")
        record.rgb_contribution_percent = (
            {str(key): float(value) for key, value in contribution.items()}
            if isinstance(contribution, dict) else None
        )
    diagnostics_path: Path | None = None
    overlay_path: Path | None = None
    if config.background.mode == "pedestal":
        geometric, common, exclusion = background_masks(planes, config.background)
        proposal = BackgroundProposal(
            config.background.resolved_branches.get(str(planes[0].branch), {}),
            geometric, common, exclusion
        )
        run_directory = (
            png_output.parent.parent
            if png_output.parent.name == planes[0].branch else png_output.parent
        )
        paths = (
            existing_branch_artifact_paths(run_directory, planes[0].branch)
            or branch_artifact_paths(run_directory, planes[0].branch)
        )
        diagnostics_path = write_background_diagnostics(proposal, paths.background_diagnostics)
        overlay_path = write_background_overlay(proposal, paths.background_overlay)
    coverage_stage = {
        "stage_id": "presentation_coverage",
        "algorithm_ids": ["COVERAGE-001"],
        "algorithm_versions": {"presentation_coverage": "presentation-coverage-v1"},
        "parent_ids": list(rendered.composition.required_plane_ids),
        "source_content_identities": [
            {"source_id": source_id}
            for source_id in rendered.composition.required_source_ids
        ],
        "branch": planes[0].branch,
        "input_domain": "display_rgb",
        "output_domain": "display_rgb",
        "grid_id": planes[0].grid_id,
        "requested_settings": config.coverage.model_dump(mode="json"),
        "resolved_settings": rendered.coverage.diagnostics,
        "output_content_identity": {
            "sha256": hashlib.sha256(np.ascontiguousarray(rendered.rgb).tobytes()).hexdigest()
        },
    }
    return (
        export_png(rendered.rgb, png_output),
        export_tiff(rendered.rgb, tiff_output),
        result.warnings,
        rendered.background.stage_record,
        coverage_stage,
        diagnostics_path,
        overlay_path,
    )


def _string_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_selection_inputs(base: SelectionInputs, override: SelectionInputs | None) -> SelectionInputs:
    if override is None:
        return base
    return SelectionInputs(
        include_filters=set(base.include_filters) | set(override.include_filters),
        include_instruments=set(base.include_instruments) | set(override.include_instruments),
        include_missions=set(base.include_missions) | set(override.include_missions),
        include_obsids=set(base.include_obsids) | set(override.include_obsids),
        exclude_obsids=set(base.exclude_obsids) | set(override.exclude_obsids),
        include_products=set(base.include_products) | set(override.include_products),
        exclude_products=set(base.exclude_products) | set(override.exclude_products),
        strategy=override.strategy or base.strategy,
        max_per_filter=override.max_per_filter or base.max_per_filter,
        max_total=override.max_total or base.max_total,
    )


def _local_product_manifest(
    candidates: CandidateManifest, local_paths: dict[str, Path],
) -> list[dict[str, object]]:
    from galaxy.cache import sha256_file
    records: list[dict[str, object]] = []
    by_id = {item.candidate_id: item for item in candidates.candidates if item.selected}
    unknown = set(local_paths) - set(by_id)
    if unknown:
        raise ValueError(f"local product paths include unknown pins: {', '.join(sorted(unknown))}")
    for candidate_id, source in local_paths.items():
        candidate = by_id[candidate_id]
        records.append({
            "candidate_id": candidate_id,
            "product_identifier": candidate.obs_id or candidate_id,
            "stable_product_identifier": candidate_id,
            "product_filename": candidate.product_filename or source.name,
            "filter": candidate.filter_name,
            "product_type": candidate.product_type,
            "product_version": candidate.product_version,
            "selection_rank": candidate.selection_rank,
            "selected_reason": "selected:pinned_scene_card_local_asset",
            "url": candidate.data_uri,
            "local_path": str(source),
            "file_size": source.stat().st_size,
            "checksum": sha256_file(source),
            "download_timestamp": None,
            "status": "complete",
        })
    return records


def _source_ids_by_path(
    manifest: list[dict[str, object]],
    local_product_paths: dict[str, Path],
) -> dict[Path, str]:
    identities = {
        Path(path).resolve(): str(candidate_id)
        for candidate_id, path in local_product_paths.items()
    }
    for item in manifest:
        local_path = item.get("local_path")
        source_id = (
            item.get("stable_product_identifier")
            or item.get("candidate_id")
            or item.get("product_identifier")
        )
        if local_path is not None and source_id is not None:
            identities[Path(str(local_path)).resolve()] = str(source_id)
    return identities


def _validate_inspected_scene(
    card: SceneCard | None, planes: list[FITSPlane] | list[ReprojectedPlane], *,
    require_deconvolved: bool,
) -> None:
    if card is None:
        return
    plane_filters = {plane.plane_id: str(plane.metadata.get("filter") or "") for plane in planes}
    branches = ("original", "deconvolved") if require_deconvolved else ("original",)
    problems = [
        item for branch in branches
        for item in readiness(
            card, "render", plane_filters=plane_filters, branch=branch,
            inspected_plane_ids=True,
        )
    ]
    if problems:
        message = "\n".join(f"{item.path}: [{item.code}] {item.message}" for item in problems)
        raise ValueError(f"scene card is not render-ready for inspected FITS planes:\n{message}")


def _reprojection_settings(diagnostics: dict[str, object]) -> dict[str, object]:
    return {
        "mode": diagnostics.get("mode"),
        "reference_plane_id": diagnostics.get("reference_plane_id"),
        "expand_fraction": diagnostics.get("expand_fraction"),
        "pixel_scale_arcsec": diagnostics.get("pixel_scale_arcsec"),
        "width": diagnostics.get("width"),
        "height": diagnostics.get("height"),
        "projection": diagnostics.get("projection"),
        "rotation_deg": diagnostics.get("rotation_deg"),
        "center_mode": diagnostics.get("center_mode"),
        "center_ra_deg": diagnostics.get("center_ra_deg"),
        "center_dec_deg": diagnostics.get("center_dec_deg"),
        "flux_conserving": diagnostics.get("flux_conserving"),
        "reprojection_method": diagnostics.get("reprojection_method"),
        "reprojection_bytes_per_pixel": diagnostics.get("reprojection_bytes_per_pixel"),
        "estimated_peak_bytes": diagnostics.get("estimated_peak_bytes"),
        "system_memory_bytes": diagnostics.get("system_memory_bytes"),
        "memory_warning_fraction": diagnostics.get("memory_warning_fraction"),
        "bridge": diagnostics.get("bridge"),
        "deconvolved_loaded": diagnostics.get("deconvolved_loaded"),
    }


def _checkpoint_stage_records(*paths: Path | None) -> list[dict[str, object]]:
    return [
        checkpoint_stage_record(read_checkpoint_manifest(path))
        for path in paths
        if path is not None
    ]


def _finalize_artifacts(
    output_dir: Path, config_path: Path | None = None,
    inspected_plane_filters: dict[str, str] | None = None,
) -> PipelineArtifacts:
    original = existing_branch_artifact_paths(output_dir, "original")
    deconvolved = existing_branch_artifact_paths(output_dir, "deconvolved")
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=original.aligned_planes if original else None,
        deconvolved_planes_path=deconvolved.aligned_planes if deconvolved else None,
        checkpoint_manifest_path=(
            original.checkpoint_manifest if original and original.checkpoint_manifest.exists() else None
        ),
        deconvolved_checkpoint_manifest_path=(
            deconvolved.checkpoint_manifest if deconvolved and deconvolved.checkpoint_manifest.exists() else None
        ),
        footprint_overlay_path=output_dir / "footprints.png" if (output_dir / "footprints.png").exists() else None,
        png_path=original.composite_png if original and original.composite_png.exists() else None,
        deconvolved_png_path=(
            deconvolved.composite_png if deconvolved and deconvolved.composite_png.exists() else None
        ),
        tiff_path=original.composite_tiff if original and original.composite_tiff.exists() else None,
        deconvolved_tiff_path=(
            deconvolved.composite_tiff if deconvolved and deconvolved.composite_tiff.exists() else None
        ),
        background_diagnostics_path=(
            original.background_diagnostics
            if original and original.background_diagnostics.exists() else None
        ),
        deconvolved_background_diagnostics_path=(
            deconvolved.background_diagnostics
            if deconvolved and deconvolved.background_diagnostics.exists() else None
        ),
        background_overlay_path=(
            original.background_overlay if original and original.background_overlay.exists() else None
        ),
        deconvolved_background_overlay_path=(
            deconvolved.background_overlay
            if deconvolved and deconvolved.background_overlay.exists() else None
        ),
        provenance_path=output_dir / "provenance.json",
        config_path=config_path or output_dir / "scene-card-input.json",
        inspected_plane_filters=inspected_plane_filters or {},
        effective_canvas=None,
    )

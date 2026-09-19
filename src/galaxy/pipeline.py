from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable

from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS

from galaxy.cache import ensure_directory, write_manifest
from galaxy.processing_config import GalaxyConfig
from galaxy.export import export_footprint_overlay, export_png, export_tiff
from galaxy.fitsio import FITSPlane, load_fits_plane
from galaxy.logging_utils import configure_logging, emit_log
from galaxy.mapping import CompositionInputs, compose_channels
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
from galaxy.selection import CandidateManifest, SelectionInputs, write_candidate_manifest
from galaxy.scene_models import SceneCard
from galaxy.scene_readiness import readiness
from galaxy.targeting import ResolvedTarget, region_to_mast_shape, resolve_target
from galaxy.tone import apply_tone


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
    footprint_overlay_path: Path | None
    png_path: Path | None
    deconvolved_png_path: Path | None
    tiff_path: Path | None
    deconvolved_tiff_path: Path | None
    provenance_path: Path
    config_path: Path
    inspected_plane_filters: dict[str, str]


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
    reprojected_dir = ensure_directory(output_dir / "reprojected")

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

    original_records, original_planes_path = _export_branch_planes(
        original_reprojected,
        config,
        output_dir / "exported_planes.fits",
        output_wcs=reprojected_result.output_wcs,
        artifact_branch="original",
    )
    deconvolved_records: list = []
    deconvolved_planes_path: Path | None = None
    if deconvolved_reprojected:
        deconvolved_records, deconvolved_planes_path = _export_branch_planes(
            deconvolved_reprojected,
            config,
            output_dir / "exported_planes_deconvolved.fits",
            output_wcs=reprojected_result.output_wcs,
            artifact_branch="deconvolved",
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
        )
        write_provenance(provenance, output_dir / "provenance.json")
        emit_log(logger, logging.INFO, "Pipeline finished in reproject-only mode", progress)
        return _finalize_artifacts(output_dir, Path(config_path) if config_path else None)

    png_path, tiff_path = _compose_and_export_branch(
        original_reprojected,
        original_records,
        config,
        output_dir / "composite.png",
        output_dir / "composite.tiff",
    )
    deconvolved_png_path: Path | None = None
    deconvolved_tiff_path: Path | None = None
    if deconvolved_reprojected:
        deconvolved_png_path, deconvolved_tiff_path = _compose_and_export_branch(
            deconvolved_reprojected,
            deconvolved_records,
            config,
            output_dir / "composite_deconvolved.png",
            output_dir / "composite_deconvolved.tiff",
        )

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
    )
    write_provenance(provenance, output_dir / "provenance.json")
    emit_log(logger, logging.INFO, "Pipeline finished successfully", progress)
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=original_planes_path,
        deconvolved_planes_path=deconvolved_planes_path,
        footprint_overlay_path=footprint_overlay_path,
        png_path=png_path,
        deconvolved_png_path=deconvolved_png_path,
        tiff_path=tiff_path,
        deconvolved_tiff_path=deconvolved_tiff_path,
        provenance_path=output_dir / "provenance.json",
        config_path=Path(config_path) if config_path else output_dir / "scene-card-input.json",
        inspected_plane_filters={
            plane.plane_id: str(plane.metadata.get("filter") or "")
            for plane in original_reprojected
        },
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
) -> ReprojectionLoadResult:
    exported_planes = output_dir / "exported_planes.fits"
    exported_deconvolved_planes = output_dir / "exported_planes_deconvolved.fits"
    if mode == "compose-only" and exported_planes.exists():
        emit_log(logger, logging.INFO, "Compose-only mode reusing exported plane artifacts", progress)
        original_planes = load_multiplane_records(exported_planes)
        deconvolved_planes = load_multiplane_records(exported_deconvolved_planes) if exported_deconvolved_planes.exists() else []
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
    filter_skipped = 0
    load_failed = 0
    first_failure: str | None = None

    emit_log(logger, logging.INFO, f"Loading cached FITS planes from {len(cached_paths)} files", progress)

    for source_path in cached_paths:
        try:
            plane = load_fits_plane(source_path)
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

    deconvolved_fits_planes: list[FITSPlane] = []
    if config.psf.enabled:
        emit_log(logger, logging.INFO, "Building deconvolved cache companions", progress)
        deconvolved_fits_planes = build_deconvolved_plane_artifacts(fits_planes, config.psf, cache_dir)
        diagnostics["deconvolved_loaded"] = len(deconvolved_fits_planes)
        emit_log(logger, logging.INFO, f"Built {len(deconvolved_fits_planes)} deconvolved cache companions", progress)
    else:
        diagnostics["deconvolved_loaded"] = 0

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

    original_reprojected = reproject_all(fits_planes, output_wcs, shape_out, config.canvas.flux_conserving, progress=progress)
    for plane in original_reprojected:
        plane.metadata.setdefault("artifact_branch", "original")
        save_reprojected_plane(plane, output_wcs, reprojected_dir / "original")

    deconvolved_reprojected: list[ReprojectedPlane] = []
    if deconvolved_fits_planes:
        deconvolved_reprojected = reproject_all(
            deconvolved_fits_planes,
            output_wcs,
            shape_out,
            config.canvas.flux_conserving,
            progress=progress,
        )
        for plane in deconvolved_reprojected:
            plane.metadata.setdefault("artifact_branch", "deconvolved")
            save_reprojected_plane(plane, output_wcs, reprojected_dir / "deconvolved")

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
) -> tuple[Path, Path]:
    plane_arrays = {plane.plane_id: plane.data for plane in planes}
    plane_meta = {plane.plane_id: plane.metadata for plane in planes}
    enabled_planes = {record.plane_id for record in records if record.enabled}
    composed = compose_channels(CompositionInputs(planes=plane_arrays, metadata=plane_meta), config.mapping, enabled_planes)
    rgb = apply_tone(composed, config.tone, bit_depth=16)
    return export_png(rgb, png_output), export_tiff(rgb, tiff_output)


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
        for item in readiness(card, "render", plane_filters=plane_filters, branch=branch)
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
        "deconvolved_loaded": diagnostics.get("deconvolved_loaded"),
    }


def _finalize_artifacts(
    output_dir: Path, config_path: Path | None = None,
    inspected_plane_filters: dict[str, str] | None = None,
) -> PipelineArtifacts:
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=output_dir / "exported_planes.fits" if (output_dir / "exported_planes.fits").exists() else None,
        deconvolved_planes_path=output_dir / "exported_planes_deconvolved.fits" if (output_dir / "exported_planes_deconvolved.fits").exists() else None,
        footprint_overlay_path=output_dir / "footprints.png" if (output_dir / "footprints.png").exists() else None,
        png_path=output_dir / "composite.png" if (output_dir / "composite.png").exists() else None,
        deconvolved_png_path=output_dir / "composite_deconvolved.png" if (output_dir / "composite_deconvolved.png").exists() else None,
        tiff_path=output_dir / "composite.tiff" if (output_dir / "composite.tiff").exists() else None,
        deconvolved_tiff_path=output_dir / "composite_deconvolved.tiff" if (output_dir / "composite_deconvolved.tiff").exists() else None,
        provenance_path=output_dir / "provenance.json",
        config_path=config_path or output_dir / "scene-card-input.json",
        inspected_plane_filters=inspected_plane_filters or {},
    )

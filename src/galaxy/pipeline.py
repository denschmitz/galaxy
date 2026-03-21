from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable

from galaxy.cache import ensure_directory, write_manifest
from galaxy.config import GalaxyConfig, dump_config
from galaxy.export import export_png, export_tiff
from galaxy.fitsio import FITSPlane, load_fits_plane
from galaxy.mapping import CompositionInputs, compose_channels
from galaxy.mast import build_candidate_manifest, discover_candidates, download_selected, selection_summary
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_records
from galaxy.provenance import build_provenance, write_provenance
from galaxy.psf import apply_presentation_psf
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
from galaxy.targeting import region_to_mast_shape, resolve_target
from galaxy.tone import apply_tone


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineArtifacts:
    workdir: Path
    manifest_path: Path
    planes_path: Path | None
    png_path: Path | None
    tiff_path: Path | None
    provenance_path: Path
    config_path: Path


@dataclass(slots=True)
class ReprojectionLoadResult:
    planes: list[ReprojectedPlane]
    diagnostics: dict[str, object]


def run_pipeline(
    config: GalaxyConfig,
    workdir: str | Path,
    mode: str = "full",
    progress: Callable[[str], None] | None = None,
    *,
    config_path: str | None = None,
    selection_manifest: CandidateManifest | None = None,
    selection_inputs: SelectionInputs | None = None,
) -> PipelineArtifacts:
    output_dir = ensure_directory(workdir)
    cache_dir = ensure_directory(output_dir / "cache")
    reprojected_dir = ensure_directory(output_dir / "reprojected")

    resolved_target = resolve_target(config.target)
    shape_kind, shape_kwargs = region_to_mast_shape(config.target.region, resolved_target.coord)

    candidate_manifest: CandidateManifest | None = None
    execution_source = 'saved_candidate_manifest' if selection_manifest is not None else 'raw_config_discovery'
    manifest: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    cached_paths: list[Path] = sorted(cache_dir.glob("*.fits*"))

    if mode in {"full", "download-only", "reproject-only"}:
        if mode in {"full", "download-only"} or not cached_paths:
            if selection_manifest is None:
                candidates = discover_candidates(shape_kind, shape_kwargs, config.search, progress=progress)
                candidate_manifest = build_candidate_manifest(
                    candidates,
                    config.search,
                    config_path=config_path,
                    selection_inputs=selection_inputs,
                )
            else:
                if progress:
                    progress("Loaded candidate manifest for execution")
                merged_inputs = _merge_selection_inputs(selection_manifest.selection_inputs, selection_inputs)
                candidate_manifest = build_candidate_manifest(
                    selection_manifest.candidates,
                    config.search,
                    config_path=selection_manifest.config_path or config_path,
                    selection_inputs=merged_inputs,
                )

            write_candidate_manifest(candidate_manifest, output_dir / "candidates.json")
            if progress:
                progress(f"Candidate manifest write location: {output_dir / 'candidates.json'}")
            summary = selection_summary(candidate_manifest.candidates)
            if progress:
                progress(f"Automatic selection result count: {summary['auto_selected_count']}")
                progress(f"Final explicit selection result count: {summary['selected_count']}")
                if summary["filters"]:
                    progress(f"Available filters: {', '.join(summary['filters'])}")
                if summary["instruments"]:
                    progress(f"Available instruments: {', '.join(summary['instruments'])}")

            selected_candidates = [candidate for candidate in candidate_manifest.candidates if candidate.selected]
            if not selected_candidates:
                raise RuntimeError(
                    "archive discovery produced no selected candidates; adjust the selection policy, explicit overrides, or base search filters"
                )
            manifest, skipped = download_selected(candidate_manifest.candidates, cache_dir, progress=progress)
            write_manifest(manifest, output_dir / "manifest.json")
            cached_paths = [Path(entry["local_path"]) for entry in manifest]
            if progress:
                progress(f"Downloaded or reused {len(cached_paths)} FITS files")
            if not cached_paths:
                first_reason = skipped[0]["reason"] if skipped else "none recorded"
                raise RuntimeError(
                    f"all selected candidate downloads failed or were skipped (selected={len(selected_candidates)}, skipped={len(skipped)}). "
                    f"First failure: {first_reason}"
                )

    if mode == "download-only":
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
        dump_config(config, output_dir / "run_config.yaml")
        return _finalize_artifacts(output_dir)

    reprojected_result = _load_or_build_reprojected(
        config,
        resolved_target.coord,
        cached_paths,
        output_dir,
        reprojected_dir,
        mode,
        progress,
    )
    reprojected = reprojected_result.planes
    if not reprojected:
        diagnostics = reprojected_result.diagnostics
        raise RuntimeError(
            "no usable planes were available for reprojection or composition "
            f"(cached_fits={diagnostics['cached_fits']}, loaded={diagnostics['loaded']}, "
            f"filter_skipped={diagnostics['filter_skipped']}, load_failed={diagnostics['load_failed']}). "
            f"First failure: {diagnostics['first_failure'] or 'none recorded'}"
        )

    plane_records = build_plane_records(reprojected, set(config.planes.disabled_plane_ids))
    plane_arrays = {plane.plane_id: plane.data for plane in reprojected}
    plane_meta = {plane.plane_id: plane.metadata for plane in reprojected}
    plane_arrays = apply_presentation_psf(plane_arrays, config.psf)

    planes_path: Path | None = None
    if config.planes.export_multiplane_fits:
        planes_path = export_multiplane_fits(reprojected, output_dir / "exported_planes.fits")

    if mode == "reproject-only":
        provenance = build_provenance(
            config,
            resolved_target,
            manifest,
            skipped,
            plane_records,
            _reprojection_settings(reprojected_result.diagnostics),
            candidate_manifest,
            execution_source,
        )
        write_provenance(provenance, output_dir / "provenance.json")
        dump_config(config, output_dir / "run_config.yaml")
        return _finalize_artifacts(output_dir)

    enabled_planes = {record.plane_id for record in plane_records if record.enabled}
    composed = compose_channels(CompositionInputs(planes=plane_arrays, metadata=plane_meta), config.mapping, enabled_planes)
    rgb = apply_tone(composed, config.tone, bit_depth=16)

    png_path = export_png(rgb, output_dir / "composite.png")
    tiff_path = export_tiff(rgb, output_dir / "composite.tiff")

    provenance = build_provenance(
        config,
        resolved_target,
        manifest,
        skipped,
        plane_records,
        _reprojection_settings(reprojected_result.diagnostics),
        candidate_manifest,
        execution_source,
    )
    write_provenance(provenance, output_dir / "provenance.json")
    dump_config(config, output_dir / "run_config.yaml")
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=planes_path,
        png_path=png_path,
        tiff_path=tiff_path,
        provenance_path=output_dir / "provenance.json",
        config_path=output_dir / "run_config.yaml",
    )


def _load_or_build_reprojected(
    config: GalaxyConfig,
    resolved_center,
    cached_paths: list[Path],
    output_dir: Path,
    reprojected_dir: Path,
    mode: str,
    progress: Callable[[str], None] | None,
) -> ReprojectionLoadResult:
    exported_planes = output_dir / "exported_planes.fits"
    if mode == "compose-only" and exported_planes.exists():
        planes = load_multiplane_records(exported_planes)
        return ReprojectionLoadResult(
            planes=planes,
            diagnostics={
                "mode": "compose_only_export",
                "reference_plane_id": None,
                "expand_fraction": 0.10,
                "pixel_scale_arcsec": None,
                "width": planes[0].data.shape[1] if planes else 0,
                "height": planes[0].data.shape[0] if planes else 0,
                "cached_fits": 0,
                "loaded": len(planes),
                "filter_skipped": 0,
                "load_failed": 0,
                "first_failure": None,
            },
        )

    fits_planes: list[FITSPlane] = []
    filter_skipped = 0
    load_failed = 0
    first_failure: str | None = None

    if progress:
        progress(f"Loading cached FITS planes from {len(cached_paths)} files")

    for source_path in cached_paths:
        try:
            plane = load_fits_plane(source_path)
            plane_filter = str(plane.metadata.get("filter") or "")
            if config.planes.enabled_filters and plane_filter not in config.planes.enabled_filters:
                filter_skipped += 1
                if progress:
                    progress(f"Skipping {source_path.name}: filter '{plane_filter or 'unknown'}' not in enabled_filters")
                continue
            fits_planes.append(plane)
        except Exception as exc:
            load_failed += 1
            if first_failure is None:
                first_failure = f"{source_path.name}: {exc}"
            if progress:
                progress(f"Skipping {source_path.name}: {exc}")
            if config.execution.fail_fast:
                raise

    diagnostics = {
        "cached_fits": len(cached_paths),
        "loaded": len(fits_planes),
        "filter_skipped": filter_skipped,
        "load_failed": load_failed,
        "first_failure": first_failure,
    }

    if progress:
        progress(
            f"Loaded {len(fits_planes)} usable FITS planes "
            f"(filter_skipped={filter_skipped}, load_failed={load_failed})"
        )

    if not fits_planes:
        return ReprojectionLoadResult(planes=[], diagnostics=diagnostics)

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
        len(fits_planes),
        reprojection_bytes_per_pixel,
        reprojection_method,
    )
    system_memory_bytes = get_system_memory_bytes()
    canvas_diag.update({
        "estimated_peak_bytes": estimated_peak_bytes,
        "system_memory_bytes": system_memory_bytes,
        "memory_warning_fraction": MEMORY_WARNING_FRACTION,
    })
    diagnostics.update(canvas_diag)
    if progress:
        progress(
            f"Using configured canvas workspace {shape_out[1]}x{shape_out[0]} "
            f"at {config.canvas.pixel_scale_arcsec:.3f} arcsec/pixel"
        )
    if system_memory_bytes is not None and estimated_peak_bytes >= int(system_memory_bytes * MEMORY_WARNING_FRACTION):
        warning_message = (
            "Warning: estimated reprojection working set is at or above "
            f"{int(MEMORY_WARNING_FRACTION * 100)}% of system RAM "
            f"({estimated_peak_bytes / (1024 ** 3):.1f} GiB estimated vs "
            f"{system_memory_bytes / (1024 ** 3):.1f} GiB installed)."
        )
        logger.warning(warning_message)
        if progress:
            progress(warning_message)

    reprojected = reproject_all(fits_planes, output_wcs, shape_out, config.canvas.flux_conserving, progress=progress)
    for plane in reprojected:
        save_reprojected_plane(plane, output_wcs, reprojected_dir)
    return ReprojectionLoadResult(planes=reprojected, diagnostics=diagnostics)


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
    }


def _finalize_artifacts(output_dir: Path) -> PipelineArtifacts:
    return PipelineArtifacts(
        workdir=output_dir,
        manifest_path=output_dir / "manifest.json",
        planes_path=output_dir / "exported_planes.fits" if (output_dir / "exported_planes.fits").exists() else None,
        png_path=output_dir / "composite.png" if (output_dir / "composite.png").exists() else None,
        tiff_path=output_dir / "composite.tiff" if (output_dir / "composite.tiff").exists() else None,
        provenance_path=output_dir / "provenance.json",
        config_path=output_dir / "run_config.yaml",
    )



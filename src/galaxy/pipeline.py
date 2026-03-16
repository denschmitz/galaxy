from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from galaxy.cache import ensure_directory, write_manifest
from galaxy.config import GalaxyConfig, dump_config
from galaxy.export import export_png, export_tiff
from galaxy.fitsio import FITSPlane, load_fits_plane
from galaxy.mapping import CompositionInputs, compose_channels
from galaxy.mast import download_products, query_archive, select_products
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_records
from galaxy.provenance import build_provenance, write_provenance
from galaxy.psf import apply_presentation_psf
from galaxy.reprojection import ReprojectedPlane, build_output_wcs, reproject_all, save_reprojected_plane
from galaxy.targeting import region_to_mast_shape, resolve_target
from galaxy.tone import apply_tone


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
) -> PipelineArtifacts:
    output_dir = ensure_directory(workdir)
    cache_dir = ensure_directory(output_dir / "cache")
    reprojected_dir = ensure_directory(output_dir / "reprojected")

    resolved_target = resolve_target(config.target)
    shape_kind, shape_kwargs = region_to_mast_shape(config.target.region, resolved_target.coord)

    manifest: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    cached_paths: list[Path] = sorted(cache_dir.glob("*.fits*"))

    if mode in {"full", "download-only", "reproject-only"}:
        if mode == "full" or mode == "download-only" or not cached_paths:
            if progress:
                progress("Querying MAST archive")
            search_result = query_archive(shape_kind, shape_kwargs, config.search, progress=progress)
            if progress:
                progress("Selecting deterministic product set")
            selected_products = select_products(search_result.products, config.search)
            if progress:
                progress(f"Selected {len(selected_products)} products for download")
            if not selected_products:
                raise RuntimeError(
                    "archive query returned no selectable products; adjust mission/filter/product-type constraints or widen the search"
                )
            manifest, skipped = download_products(selected_products, cache_dir, progress=progress)
            write_manifest(manifest, output_dir / "manifest.json")
            cached_paths = [Path(entry["local_path"]) for entry in manifest]
            if progress:
                progress(f"Downloaded or reused {len(cached_paths)} FITS files")
            if not cached_paths:
                first_reason = skipped[0]["reason"] if skipped else "none recorded"
                raise RuntimeError(
                    f"all selected product downloads failed or were skipped (selected={len(selected_products)}, skipped={len(skipped)}). "
                    f"First failure: {first_reason}"
                )

    if mode == "download-only":
        return _finalize_artifacts(output_dir)

    output_wcs, shape_out = build_output_wcs(config.canvas, resolved_target.coord)
    reprojected_result = _load_or_build_reprojected(
        config,
        cached_paths,
        output_dir,
        reprojected_dir,
        output_wcs,
        shape_out,
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
            _reprojection_settings(config, shape_out),
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
        _reprojection_settings(config, shape_out),
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
    cached_paths: list[Path],
    output_dir: Path,
    reprojected_dir: Path,
    output_wcs,
    shape_out: tuple[int, int],
    mode: str,
    progress: Callable[[str], None] | None,
) -> ReprojectionLoadResult:
    exported_planes = output_dir / "exported_planes.fits"
    if mode == "compose-only" and exported_planes.exists():
        planes = load_multiplane_records(exported_planes)
        return ReprojectionLoadResult(
            planes=planes,
            diagnostics={
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

    if progress:
        progress(
            f"Loaded {len(fits_planes)} usable FITS planes "
            f"(filter_skipped={filter_skipped}, load_failed={load_failed})"
        )

    reprojected = reproject_all(fits_planes, output_wcs, shape_out, config.canvas.flux_conserving, progress=progress)
    for plane in reprojected:
        save_reprojected_plane(plane, output_wcs, reprojected_dir)
    return ReprojectionLoadResult(
        planes=reprojected,
        diagnostics={
            "cached_fits": len(cached_paths),
            "loaded": len(fits_planes),
            "filter_skipped": filter_skipped,
            "load_failed": load_failed,
            "first_failure": first_failure,
        },
    )


def _reprojection_settings(config: GalaxyConfig, shape_out: tuple[int, int]) -> dict[str, object]:
    return {
        "projection": config.canvas.projection,
        "pixel_scale_arcsec": config.canvas.pixel_scale_arcsec,
        "width": shape_out[1],
        "height": shape_out[0],
        "rotation_deg": config.canvas.rotation_deg,
        "flux_conserving": config.canvas.flux_conserving,
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


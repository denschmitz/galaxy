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
from galaxy.planes import build_plane_records, export_multiplane_fits, load_multiplane_fits
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
            search_result = query_archive(shape_kind, shape_kwargs, config.search)
            selected_products = select_products(search_result.products)
            manifest, skipped = download_products(selected_products, cache_dir, progress=progress)
            write_manifest(manifest, output_dir / "manifest.json")
            cached_paths = [Path(entry["local_path"]) for entry in manifest]

    if mode == "download-only":
        return _finalize_artifacts(output_dir)

    output_wcs, shape_out = build_output_wcs(config.canvas, resolved_target.coord)
    reprojected = _load_or_build_reprojected(config, cached_paths, output_dir, reprojected_dir, output_wcs, shape_out, mode, progress)
    if not reprojected:
        raise RuntimeError("no usable planes were available for reprojection or composition")

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
) -> list[ReprojectedPlane]:
    exported_planes = output_dir / "exported_planes.fits"
    if mode == "compose-only" and exported_planes.exists():
        arrays = load_multiplane_fits(exported_planes)
        return [ReprojectedPlane(plane_id=name, data=data, footprint=data * 0 + 1, metadata={"filter": name}) for name, data in arrays.items()]

    fits_planes: list[FITSPlane] = []
    for source_path in cached_paths:
        try:
            plane = load_fits_plane(source_path)
            if config.planes.enabled_filters and str(plane.metadata.get("filter") or "") not in config.planes.enabled_filters:
                continue
            fits_planes.append(plane)
        except Exception:
            if config.execution.fail_fast:
                raise

    reprojected = reproject_all(fits_planes, output_wcs, shape_out, config.canvas.flux_conserving, progress=progress)
    for plane in reprojected:
        save_reprojected_plane(plane, output_wcs, reprojected_dir)
    return reprojected


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

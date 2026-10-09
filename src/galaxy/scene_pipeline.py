"""Canonical JSON scene-card pipeline entrypoint."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .pipeline import PipelineArtifacts, run_pipeline
from .scene_card import append_render, edit_scene, load_scene, save_scene
from .scene_execution import prepare_scene_execution
from .scene_models import Asset, SceneCard, effective_inputs


@dataclass(frozen=True, slots=True)
class ScenePipelineResult:
    card: SceneCard
    artifacts: PipelineArtifacts


def default_scene_workdir(card_path: str | Path, revision: int) -> Path:
    source = Path(card_path).resolve()
    from .scene_workflow import associated_asset_root
    return associated_asset_root(source) / f"render-r{revision}-{uuid4().hex[:12]}"


def run_scene_pipeline(
    card_path: str | Path,
    workdir: str | Path | None = None,
    mode: str = "full",
    progress: Callable[[str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> ScenePipelineResult:
    """Run exact scene pins and append successful composed branches atomically."""
    source = Path(card_path).resolve()
    card = load_scene(source)
    launch = prepare_scene_execution(card, source)
    output_dir = default_scene_workdir(source, card.content_revision) if workdir is None else Path(workdir).resolve()
    if not output_dir.is_relative_to(source.parent):
        raise ValueError("scene workdir must remain inside the scene card directory")
    if output_dir == source.parent:
        raise ValueError("scene workdir must be a dedicated child directory")
    _reject_registered_output_overlap(card, source, output_dir)
    artifacts = run_pipeline(
        launch.config,
        output_dir,
        mode=mode,
        progress=progress,
        config_path=str(source),
        selection_manifest=launch.selection_manifest,
        pinned_selection=True,
        local_product_paths=launch.local_product_paths,
        scene_card=launch.card,
        cancel_requested=cancel_requested,
    )
    if cancel_requested is not None and cancel_requested():
        from .pipeline import PipelineCancelled
        raise PipelineCancelled("render cancelled before scene history commit")
    render_card = (
        edit_scene(launch.card, {"canvas": artifacts.effective_canvas})
        if artifacts.effective_canvas is not None else launch.card
    )
    updated = render_card
    if mode not in ("full", "compose-only"):
        return ScenePipelineResult(updated, artifacts)

    plane_filters = _plane_filters(artifacts)
    provenance_id = f"provenance-{uuid4()}"
    common = {
        provenance_id: _local_asset("provenance", artifacts.provenance_path, source),
    }
    candidates_path = artifacts.workdir / "candidates.json"
    if candidates_path.is_file():
        common[f"candidates-{uuid4()}"] = _local_asset("candidate_manifest", candidates_path, source)
    if artifacts.footprint_overlay_path is not None:
        footprint_id = f"footprint-{uuid4()}"
        common[footprint_id] = _local_asset("footprint", artifacts.footprint_overlay_path, source)
    else:
        footprint_id = None

    branches = [
        ("original", artifacts.png_path, artifacts.tiff_path, artifacts.planes_path,
         artifacts.checkpoint_manifest_path, artifacts.background_diagnostics_path,
         artifacts.background_overlay_path),
        ("deconvolved", artifacts.deconvolved_png_path, artifacts.deconvolved_tiff_path,
         artifacts.deconvolved_planes_path, artifacts.deconvolved_checkpoint_manifest_path,
         artifacts.deconvolved_background_diagnostics_path,
         artifacts.deconvolved_background_overlay_path),
    ]
    for (
        branch, image_path, tiff_path, planes_path, checkpoint_path,
        background_diagnostics_path, background_overlay_path,
    ) in branches:
        if image_path is None:
            continue
        image_id = f"render-{uuid4()}"
        thumbnail_path = _make_thumbnail(image_path)
        thumbnail_id = f"thumbnail-{uuid4()}"
        branch_assets = {
            **common,
            image_id: _local_asset("render_image", image_path, source),
            thumbnail_id: _local_asset("render_thumbnail", thumbnail_path, source),
        }
        if tiff_path is not None:
            high_depth_id = f"render-tiff-{uuid4()}"
            branch_assets[high_depth_id] = _local_asset("render_image", tiff_path, source)
        else:
            high_depth_id = None
        if checkpoint_path is not None:
            checkpoint_id = f"checkpoint-{uuid4()}"
            branch_assets[checkpoint_id] = _local_asset("checkpoint_manifest", checkpoint_path, source)
        else:
            checkpoint_id = None
        background_ids: list[str] = []
        if background_diagnostics_path is not None:
            diagnostics_id = f"background-diagnostic-{uuid4()}"
            background_ids.append(diagnostics_id)
            branch_assets[diagnostics_id] = _local_asset(
                "background_diagnostic", background_diagnostics_path, source
            )
        if background_overlay_path is not None:
            overlay_id = f"background-overlay-{uuid4()}"
            background_ids.append(overlay_id)
            branch_assets[overlay_id] = _local_asset(
                "background_region_overlay", background_overlay_path, source
            )
        aligned_ids: list[str] = []
        if planes_path is not None:
            planes_id = f"planes-{uuid4()}"
            aligned_ids.append(planes_id)
            branch_assets[planes_id] = _local_asset("aligned_planes", planes_path, source)
        updated = append_render(
            updated,
            snapshot=render_card,
            branch=branch,
            plane_filters=plane_filters,
            image_asset_id=image_id,
            provenance_asset_id=provenance_id,
            assets=branch_assets,
            thumbnail_asset_id=thumbnail_id,
            high_depth_image_asset_id=high_depth_id,
            checkpoint_manifest_asset_id=checkpoint_id,
            background_diagnostic_asset_ids=background_ids,
            aligned_plane_asset_ids=aligned_ids,
            footprint_asset_id=footprint_id,
            now=None,
        )
    latest_on_disk = load_scene(source)
    latest = latest_on_disk
    if artifacts.effective_canvas is not None:
        if effective_inputs(latest) != effective_inputs(launch.card):
            raise ValueError("scene inputs changed while the automatic footprint frame was rendering")
        latest = edit_scene(latest, {"canvas": artifacts.effective_canvas})
    from .scene_workflow import merge_render_completion
    merged = merge_render_completion(latest, updated)
    if cancel_requested is not None and cancel_requested():
        from .pipeline import PipelineCancelled
        raise PipelineCancelled("render cancelled before scene history commit")
    committed = save_scene(merged, source, expected_previous=latest_on_disk)
    return ScenePipelineResult(committed, artifacts)


def _local_asset(kind: str, path: Path, card_path: Path) -> Asset:
    from .cache import sha256_file
    resolved = path.resolve()
    relative = resolved.relative_to(card_path.parent).as_posix()
    return Asset(
        kind=kind,
        path=relative,
        byte_count=resolved.stat().st_size,
        sha256=sha256_file(resolved),
    )


def _make_thumbnail(image_path: Path, maximum_size: tuple[int, int] = (480, 480)) -> Path:
    from PIL import Image
    destination = image_path.with_name(f"{image_path.stem}_thumbnail.png")
    with Image.open(image_path) as source:
        preview = source.convert("RGB")
        preview.thumbnail(maximum_size)
        preview.save(destination, format="PNG")
    return destination


def _reject_registered_output_overlap(card: SceneCard, card_path: Path, output_dir: Path) -> None:
    from .scene_card import asset_path
    for asset_id, asset in (card.assets or {}).items():
        if asset.path is None:
            continue
        registered = asset_path(card_path, asset)
        if registered == output_dir or registered.is_relative_to(output_dir):
            raise ValueError(
                f"scene workdir contains immutable registered asset {asset_id}; use a new child directory"
            )


def _plane_filters(artifacts: PipelineArtifacts) -> dict[str, str]:
    if not artifacts.inspected_plane_filters:
        raise ValueError("successful composition did not retain inspected plane metadata")
    return artifacts.inspected_plane_filters

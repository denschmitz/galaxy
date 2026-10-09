"""Build a non-destructive Phase 3 pedestal candidate from a retained render."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from astropy.coordinates import SkyCoord
import astropy.units as u

from galaxy.background import (
    estimate_background,
    write_background_diagnostics,
    write_background_overlay,
)
from galaxy.export import export_png, export_tiff
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import (
    BackgroundConfig,
    BackgroundEstimatorConfig,
    CanvasConfig,
    MappingConfig,
    SkyRectangleConfig,
    ToneConfig,
)
from galaxy.rendering import render_aligned_planes
from galaxy.reprojection import build_output_wcs
from galaxy.scene_card import asset_path, document, load_scene


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene", type=Path)
    parser.add_argument("aligned_asset_id")
    parser.add_argument("--center-x", type=float, required=True)
    parser.add_argument("--center-y", type=float, required=True)
    parser.add_argument("--width-pixels", type=float, required=True)
    parser.add_argument("--height-pixels", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-samples", type=int, default=256)
    args = parser.parse_args()

    scene_path = args.scene.resolve()
    card = load_scene(scene_path)
    asset = (card.assets or {}).get(args.aligned_asset_id)
    if asset is None or asset.kind != "aligned_planes":
        raise ValueError("aligned_asset_id must reference an aligned_planes asset")
    render = next(
        (record for record in reversed(card.renders or [])
         if args.aligned_asset_id in (record.aligned_plane_asset_ids or [])),
        None,
    )
    if render is None:
        raise ValueError("aligned asset is not referenced by render history")
    canvas_data = document(render.inputs.canvas)
    canvas_data.pop("frame_origin", None)
    canvas_data.pop("view_state", None)
    canvas = CanvasConfig.model_validate(canvas_data)
    center = SkyCoord(canvas.center.ra_deg * u.deg, canvas.center.dec_deg * u.deg)
    fallback_wcs, shape = build_output_wcs(canvas, center)
    planes = load_multiplane_records(
        asset_path(scene_path, asset), legacy_fallback_wcs=fallback_wcs
    )
    if planes[0].data.shape != shape:
        raise ValueError(
            f"scene canvas shape {shape} does not match aligned artifact {planes[0].data.shape}"
        )
    ra, dec = fallback_wcs.pixel_to_world_values(args.center_x, args.center_y)
    background = BackgroundConfig(
        mode="pedestal",
        black_reference_policy="corrected_zero",
        inclusion_regions=[SkyRectangleConfig(
            region_id="source-poor-sky",
            center_ra_deg=float(ra),
            center_dec_deg=float(dec),
            width_arcsec=args.width_pixels * canvas.pixel_scale_arcsec,
            height_arcsec=args.height_pixels * canvas.pixel_scale_arcsec,
        )],
        estimator=BackgroundEstimatorConfig(
            clip_sigma=3.0,
            max_iterations=5,
            minimum_samples=args.minimum_samples,
            minimum_valid_fraction=0.5,
        ),
    )
    proposal = estimate_background(planes, background)
    applied = BackgroundConfig.model_validate({
        **background.model_dump(mode="json"),
        "resolved_branches": {
            render.branch: {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in proposal.resolved_planes.items()
            }
        },
    })
    rendered = render_aligned_planes(
        planes,
        MappingConfig.model_validate(document(render.inputs.mapping)),
        ToneConfig.model_validate(document(render.inputs.tone)),
        bit_depth=16,
        background=applied,
    )
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    export_png(rendered.rgb, output / "candidate.png")
    export_tiff(rendered.rgb, output / "candidate.tiff")
    write_background_overlay(proposal, output / "background-regions.png")
    write_background_diagnostics(proposal, output / "background-diagnostics.json")
    report = {
        "scene": str(scene_path),
        "aligned_asset_id": args.aligned_asset_id,
        "branch": render.branch,
        "region": background.inclusion_regions[0].model_dump(mode="json"),
        "planes": {
            key: value.model_dump(mode="json", exclude_none=True)
            for key, value in proposal.resolved_planes.items()
        },
        "outputs": {
            "png": "candidate.png",
            "tiff": "candidate.tiff",
            "overlay": "background-regions.png",
            "diagnostics": "background-diagnostics.json",
        },
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

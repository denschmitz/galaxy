from __future__ import annotations

import argparse
import json
from pathlib import Path

from astropy.coordinates import SkyCoord

from galaxy.export import export_png
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import (
    BackgroundConfig, CanvasConfig, CoverageConfig, MappingConfig, ToneConfig,
)
from galaxy.rendering import render_aligned_planes
from galaxy.reprojection import build_output_wcs
from galaxy.scene_card import asset_path, document, load_scene


def generate(scene_path: Path, output_root: Path) -> dict[str, object]:
    card = load_scene(scene_path)
    render = next(
        (item for item in reversed(card.renders or []) if item.branch == "original" and item.aligned_plane_asset_ids),
        None,
    )
    if render is None:
        raise ValueError(f"scene has no original aligned-plane render: {scene_path}")
    asset_id = render.aligned_plane_asset_ids[0]
    aligned_path = asset_path(scene_path, (card.assets or {})[asset_id])
    legacy_fallback = False
    try:
        planes = load_multiplane_records(aligned_path)
    except ValueError as exc:
        if "requires a two-dimensional celestial WCS" not in str(exc):
            raise
        canvas_data = document(card.canvas)
        canvas_data.pop("view_state", None)
        canvas_data.pop("frame_origin", None)
        canvas = CanvasConfig.model_validate(canvas_data)
        center = SkyCoord(canvas.center.ra_deg, canvas.center.dec_deg, unit="deg")
        fallback_wcs, _ = build_output_wcs(canvas, center)
        planes = load_multiplane_records(aligned_path, legacy_fallback_wcs=fallback_wcs)
        legacy_fallback = True
    mapping = MappingConfig.model_validate(document(card.mapping))
    tone = ToneConfig.model_validate(document(card.tone))
    background = BackgroundConfig.model_validate(
        document(card.background) if card.background is not None else {}
    )
    destination = output_root / scene_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    modes = {
        "available": CoverageConfig(),
        "accepted-union-common-tone": CoverageConfig(
            tone_reference="common_required_bands"
        ),
        "common": CoverageConfig(
            policy="common_required_bands", tone_reference="common_required_bands",
        ),
        "common-crop": CoverageConfig(
            policy="common_required_bands", tone_reference="common_required_bands",
            crop="bounding_box",
        ),
    }
    report: dict[str, object] = {
        "scene": str(scene_path), "title": card.title, "aligned_planes": str(aligned_path),
        "legacy_fallback_wcs_used": legacy_fallback,
        "candidates": {},
    }
    for name, coverage in modes.items():
        try:
            rendered = render_aligned_planes(
                planes, mapping, tone, bit_depth=16, background=background, coverage=coverage,
            )
            image_path = export_png(rendered.rgb, destination / f"{name}.png")
            report["candidates"][name] = {
                "image": str(image_path), **rendered.coverage.diagnostics,
            }
        except ValueError as exc:
            report["candidates"][name] = {"error": str(exc)}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenes", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase4-coverage"))
    args = parser.parse_args()
    reports: list[dict[str, object]] = []
    for scene in args.scenes:
        try:
            reports.append(generate(scene, args.output))
        except (OSError, ValueError) as exc:
            reports.append({"scene": str(scene), "error": str(exc)})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(reports, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(reports, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

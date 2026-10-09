from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord

from galaxy.background import background_masks, background_selection_key
from galaxy.export import export_png
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import (
    BackgroundConfig, CanvasConfig, CoverageConfig, MappingConfig, ToneConfig,
)
from galaxy.rendering import render_aligned_planes
from galaxy.reprojection import build_output_wcs
from galaxy.scene_card import asset_path, document, load_scene
from galaxy.tone import propose_auto_stretch


def _load_planes(scene_path: Path):
    card = load_scene(scene_path)
    render = next(
        (item for item in reversed(card.renders or [])
         if item.branch == "original" and item.aligned_plane_asset_ids), None,
    )
    if render is None:
        raise ValueError(f"scene has no original aligned-plane render: {scene_path}")
    aligned_path = asset_path(scene_path, (card.assets or {})[render.aligned_plane_asset_ids[0]])
    fallback = False
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
        wcs, _ = build_output_wcs(canvas, center)
        planes = load_multiplane_records(aligned_path, legacy_fallback_wcs=wcs)
        fallback = True
    return card, aligned_path, planes, fallback


def _single_main_mapping(mapping: MappingConfig) -> MappingConfig:
    data = mapping.model_dump(mode="json")
    data["defaults"]["normalization"].update(
        {"stretch": "linear", "stretch_parameter": 1.0}
    )
    for entry in data["planes"]:
        if entry.get("normalization") is not None:
            entry["normalization"].update(
                {"stretch": "linear", "stretch_parameter": 1.0}
            )
    return MappingConfig.model_validate(data)


def _tone(base: ToneConfig, stretch: dict[str, object]) -> ToneConfig:
    data = base.model_dump(mode="json")
    data.update({
        "application": "shared_intensity", "shared_stretch": stretch,
        "gamut_policy": "rescale", "auto_stretch": None,
    })
    data.pop("auto_stretch", None)
    return ToneConfig.model_validate(data)


def _metrics(rgb: np.ndarray, support: np.ndarray) -> dict[str, object]:
    selected = np.asarray(rgb, dtype=np.float64)[np.asarray(support, dtype=bool)]
    intensity = selected.mean(axis=-1)
    return {
        "supported_pixel_count": int(selected.shape[0]),
        "intensity_percentiles": {
            str(q): float(np.percentile(intensity, q)) for q in (1, 50, 99)
        },
        "channel_at_max_fraction": float(np.count_nonzero(selected >= 65535.0) / selected.size),
        "distinct_uint16_values": int(np.unique(selected.astype(np.uint16)).size),
    }


def generate(scene_path: Path, output_root: Path) -> dict[str, object]:
    card, aligned_path, planes, fallback = _load_planes(scene_path)
    mapping = MappingConfig.model_validate(document(card.mapping))
    single_mapping = _single_main_mapping(mapping)
    legacy = ToneConfig.model_validate(document(card.tone))
    background = BackgroundConfig.model_validate(
        document(card.background) if card.background is not None else {}
    )
    coverage = CoverageConfig.model_validate(
        document(card.coverage) if card.coverage is not None else {
            "policy": "available_contributors", "tone_reference": "common_required_bands",
        }
    )
    tones = {
        "legacy": (mapping, legacy),
        "shared-asinh": (mapping, _tone(legacy, {"kind": "asinh", "parameter": 4.0})),
        "single-main-asinh": (
            single_mapping, _tone(legacy, {"kind": "asinh", "parameter": 4.0}),
        ),
        "single-main-ghs": (
            single_mapping, _tone(legacy, {
                "kind": "ghs", "stretch_factor": 2.0, "local_intensity": 3.0,
                "symmetry_point": 0.1, "shadow_protection": 0.0,
                "highlight_protection": 0.9,
            }),
        ),
    }
    destination = output_root / scene_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "scene": str(scene_path), "title": card.title,
        "aligned_planes": str(aligned_path), "legacy_fallback_wcs_used": fallback,
        "candidates": {},
    }
    for name, (candidate_mapping, candidate_tone) in tones.items():
        rendered = render_aligned_planes(
            planes, candidate_mapping, candidate_tone, bit_depth=16,
            background=background, coverage=coverage,
        )
        image_path = export_png(rendered.rgb, destination / f"{name}.png")
        y_slice, x_slice = rendered.coverage.crop_slices
        support = rendered.coverage.support[y_slice, x_slice]
        report["candidates"][name] = {
            "image": str(image_path), "tone": candidate_tone.model_dump(mode="json"),
            **_metrics(rendered.rgb, support),
        }

    if background.inclusion_regions:
        try:
            linear_tone = _tone(legacy, {"kind": "linear"})
            linear = render_aligned_planes(
                planes, single_mapping, linear_tone, bit_depth=16,
                background=background, coverage=coverage,
            )
            _, sample_mask, _ = background_masks(planes, background)
            y_slice, x_slice = linear.coverage.crop_slices
            reference = propose_auto_stretch(
                linear.rgb / 65535.0, sample_mask[y_slice, x_slice],
                reference_id=background_selection_key(planes, background),
                branch="original", grid_id=str(planes[0].grid_id),
                source_ids=list(dict.fromkeys(
                    source for plane in planes for source in plane.source_ids
                )), minimum_samples=background.estimator.minimum_samples,
            )
            auto_data = _tone(
                legacy, {"kind": "asinh", "parameter": reference.resolved_parameter}
            ).model_dump(mode="json")
            auto_data["auto_stretch"] = reference.model_dump(mode="json")
            auto_tone = ToneConfig.model_validate(auto_data)
            auto = render_aligned_planes(
                planes, single_mapping, auto_tone, bit_depth=16,
                background=background, coverage=coverage,
            )
            image_path = export_png(auto.rgb, destination / "auto-shared-asinh.png")
            support = auto.coverage.support[y_slice, x_slice]
            report["candidates"]["auto-shared-asinh"] = {
                "image": str(image_path), "tone": auto_tone.model_dump(mode="json"),
                **_metrics(auto.rgb, support),
            }
        except ValueError as exc:
            report["candidates"]["auto-shared-asinh"] = {"error": str(exc)}
    else:
        report["candidates"]["auto-shared-asinh"] = {
            "error": "scene has no persisted background regions"
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenes", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase5-stretch"))
    args = parser.parse_args()
    reports = []
    for scene in args.scenes:
        try:
            reports.append(generate(scene, args.output))
        except (OSError, ValueError) as exc:
            reports.append({"scene": str(scene), "error": str(exc)})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(reports, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(reports, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

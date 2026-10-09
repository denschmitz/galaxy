from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from galaxy.background import BackgroundApplication, apply_background
from galaxy.coverage import CoverageApplication, apply_coverage_policy, crop_rendered_rgb
from galaxy.mapping import CompositionInputs, CompositionResult, compose_channels_with_diagnostics
from galaxy.processing_config import BackgroundConfig, CoverageConfig, MappingConfig, ToneConfig
from galaxy.reprojection import ReprojectedPlane
from galaxy.tone import apply_tone


@dataclass(slots=True)
class AlignedRenderResult:
    rgb: np.ndarray
    composition: CompositionResult
    background: BackgroundApplication
    coverage: CoverageApplication


def render_aligned_planes(
    planes: list[ReprojectedPlane],
    mapping: MappingConfig,
    tone: ToneConfig,
    *,
    enabled_planes: set[str] | None = None,
    bit_depth: int = 16,
    background: BackgroundConfig | None = None,
    coverage: CoverageConfig | None = None,
) -> AlignedRenderResult:
    if not planes:
        raise ValueError("aligned rendering requires at least one plane")
    background_config = background or BackgroundConfig()
    background_result = apply_background(planes, background_config)
    composition = compose_channels_with_diagnostics(
        CompositionInputs({plane.plane_id: plane for plane in background_result.planes}),
        mapping,
        enabled_planes,
        black_reference_policy=background_config.black_reference_policy,
    )
    coverage_result = apply_coverage_policy(
        composition,
        coverage or CoverageConfig(),
        wcs=background_result.planes[0].wcs,
    )
    rgb = apply_tone(
        composition.channels,
        tone,
        bit_depth=bit_depth,
        valid_masks=coverage_result.output_masks,
        statistics_masks=coverage_result.tone_masks,
        black_reference_policy=background_config.black_reference_policy,
    )
    rgb = crop_rendered_rgb(rgb, coverage_result)
    return AlignedRenderResult(
        rgb=rgb, composition=composition, background=background_result, coverage=coverage_result
    )

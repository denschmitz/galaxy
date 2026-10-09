from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np

from galaxy.background import BackgroundSamplingError, background_masks
from galaxy.processing_config import BackgroundConfig, CoverageConfig, NormalizationReferenceConfig
from galaxy.reprojection import ReprojectedPlane


NORMALIZATION_REFERENCE_VERSION = "normalization-reference-v1"


@dataclass(frozen=True, slots=True)
class NormalizationReferenceProposal:
    references: dict[str, NormalizationReferenceConfig]
    sample_mask: np.ndarray


def estimate_normalization_references(
    planes: list[ReprojectedPlane],
    background: BackgroundConfig,
    coverage: CoverageConfig,
    *,
    black_percentile: float,
    white_percentile: float,
) -> NormalizationReferenceProposal:
    if not 0 <= black_percentile < white_percentile <= 100:
        raise ValueError("normalization reference percentiles must satisfy 0 <= black < white <= 100")
    if not background.inclusion_regions:
        raise BackgroundSamplingError("normalization reference requires a persisted inclusion region")
    _, common, _ = background_masks(planes, background)
    sample_count = int(np.count_nonzero(common))
    if sample_count == 0:
        raise BackgroundSamplingError("normalization reference region has no common valid samples")

    first = planes[0]
    region_ids = [region.region_id for region in background.inclusion_regions]
    payload = {
        "algorithm_version": NORMALIZATION_REFERENCE_VERSION,
        "region_ids": region_ids,
        "exclusion_ids": [region.region_id for region in background.exclusion_regions],
        "branch": first.branch,
        "grid_id": first.grid_id,
        "planes": [
            {"plane_id": plane.plane_id, "source_ids": list(plane.source_ids)}
            for plane in planes
        ],
        "coverage_policy": coverage.policy,
        "black_percentile": black_percentile,
        "white_percentile": white_percentile,
    }
    reference_id = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()

    references: dict[str, NormalizationReferenceConfig] = {}
    for plane in planes:
        values = np.asarray(plane.data, dtype=np.float64)[common]
        black = float(np.percentile(values, black_percentile))
        white = float(np.percentile(values, white_percentile))
        if not np.isfinite(black) or not np.isfinite(white) or white <= black:
            raise BackgroundSamplingError(
                f"normalization reference for plane '{plane.plane_id}' is constant or nonfinite"
            )
        references[plane.plane_id] = NormalizationReferenceConfig(
            reference_id=reference_id,
            region_ids=region_ids,
            branch=plane.branch,
            grid_id=str(plane.grid_id),
            source_ids=list(plane.source_ids),
            unit=plane.unit,
            coverage_policy=coverage.policy,
            tone_reference_policy=coverage.tone_reference,
            black_percentile=black_percentile,
            white_percentile=white_percentile,
            black_value=black,
            white_value=white,
            sample_count=sample_count,
            low_clipping_fraction=float(np.count_nonzero(values < black) / sample_count),
            high_clipping_fraction=float(np.count_nonzero(values > white) / sample_count),
        )
    return NormalizationReferenceProposal(references, common)

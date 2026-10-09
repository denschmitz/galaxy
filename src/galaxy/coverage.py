from __future__ import annotations

from dataclasses import dataclass

from astropy.wcs import WCS
import numpy as np
from scipy.ndimage import label

from galaxy.mapping import CompositionResult
from galaxy.processing_config import CoverageConfig


@dataclass(frozen=True, slots=True)
class CoverageApplication:
    output_masks: dict[str, np.ndarray]
    tone_masks: dict[str, np.ndarray]
    support: np.ndarray
    crop_slices: tuple[slice, slice]
    output_wcs: WCS | None
    diagnostics: dict[str, object]


def apply_coverage_policy(
    composition: CompositionResult,
    config: CoverageConfig,
    *,
    wcs: WCS | None = None,
) -> CoverageApplication:
    channel_masks = {
        key: np.asarray(value, dtype=bool) for key, value in composition.channel_coverage.items()
    }
    union = np.logical_or.reduce(list(channel_masks.values()))
    common = np.asarray(composition.required_support, dtype=bool)
    common_statistics = composition.required_statistics_support
    if common_statistics is None:
        common_statistics = common
    statistics_masks = composition.channel_statistics or channel_masks
    requires_common = (
        config.policy == "common_required_bands"
        or config.tone_reference == "common_required_bands"
    )
    if requires_common and not np.any(common):
        planes = ", ".join(composition.required_plane_ids)
        raise ValueError(f"common required-band support is empty for: {planes}")
    support = common if config.policy == "common_required_bands" else union
    output_masks = (
        {key: common.copy() for key in channel_masks}
        if config.policy == "common_required_bands"
        else channel_masks
    )
    tone_masks = (
        {key: common_statistics.copy() for key in channel_masks}
        if config.tone_reference == "common_required_bands"
        else statistics_masks
    )
    if config.tone_reference == "common_required_bands" and not np.any(common_statistics):
        raise ValueError("common observed statistics support is empty")
    if not np.any(support):
        raise ValueError("presentation support is empty")

    y_slice, x_slice = _crop_slices(support, config)
    output_wcs = None if wcs is None else wcs.deepcopy()
    if output_wcs is not None and config.crop == "bounding_box":
        output_wcs = output_wcs.slice((y_slice, x_slice))

    _, component_count = label(support, structure=np.ones((3, 3), dtype=np.uint8))
    union_count = int(np.count_nonzero(union))
    common_count = int(np.count_nonzero(common))
    diagnostics: dict[str, object] = {
        "policy": config.policy,
        "tone_reference": config.tone_reference,
        "crop": config.crop,
        "padding_pixels": config.padding_pixels,
        "required_plane_ids": list(composition.required_plane_ids),
        "required_source_ids": list(composition.required_source_ids),
        "union_pixel_count": union_count,
        "common_pixel_count": common_count,
        "tone_reference_pixel_count": (
            int(np.count_nonzero(common_statistics)) if config.tone_reference == "common_required_bands"
            else int(np.count_nonzero(np.logical_or.reduce(list(statistics_masks.values()))))
        ),
        "common_to_union_fraction": common_count / union_count if union_count else 0.0,
        "excluded_pixel_count": int(np.count_nonzero(union & ~support)),
        "component_count": int(component_count),
        "crop_bounds_xyxy": [x_slice.start, y_slice.start, x_slice.stop, y_slice.stop],
        "output_shape": [y_slice.stop - y_slice.start, x_slice.stop - x_slice.start],
    }
    return CoverageApplication(
        output_masks, tone_masks, support, (y_slice, x_slice), output_wcs, diagnostics
    )


def crop_rendered_rgb(rgb: np.ndarray, application: CoverageApplication) -> np.ndarray:
    y_slice, x_slice = application.crop_slices
    result = np.asarray(rgb).copy()
    result[~application.support] = 0
    return result[y_slice, x_slice]


def _crop_slices(support: np.ndarray, config: CoverageConfig) -> tuple[slice, slice]:
    height, width = support.shape
    if config.crop == "none":
        return slice(0, height), slice(0, width)
    ys, xs = np.nonzero(support)
    padding = config.padding_pixels
    y0 = max(int(ys.min()) - padding, 0)
    y1 = min(int(ys.max()) + 1 + padding, height)
    x0 = max(int(xs.min()) - padding, 0)
    x1 = min(int(xs.max()) + 1 + padding, width)
    return slice(y0, y1), slice(x0, x1)

"""BRIDGE-MEDIAN-001: bounded native presentation estimates, never observations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Real
from time import perf_counter
from typing import Any

import numpy as np
from scipy import ndimage

from galaxy.fitsio import FITSPlane


ALGORITHM_ID = "BRIDGE-MEDIAN-001"
ALGORITHM_VERSION = "1"


@dataclass(frozen=True, slots=True)
class BridgeProfile:
    max_area: int = 16
    max_extent: int = 8
    ring_radius: int = 2
    annulus_inner: int = 8
    annulus_outer: int = 16
    min_ring_fraction: float = 0.75
    min_annulus_fraction: float = 0.5
    min_ring_samples: int = 12
    min_annulus_samples: int = 64
    bright_sigma: float = 5.0
    min_sector_ring_samples: int = 2
    min_sector_annulus_samples: int = 8
    sector_sigma: float = 1.0
    min_declining_sectors: int = 6

    def __post_init__(self) -> None:
        for name in (
            "max_area", "max_extent", "ring_radius", "annulus_inner", "annulus_outer",
            "min_ring_samples", "min_annulus_samples", "min_sector_ring_samples",
            "min_sector_annulus_samples", "min_declining_sectors",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"bridge {name} must be a positive integer")
        for name in ("min_ring_fraction", "min_annulus_fraction", "bright_sigma", "sector_sigma"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"bridge {name} must be finite and positive")
        if self.min_ring_fraction > 1 or self.min_annulus_fraction > 1:
            raise ValueError("bridge support fractions must not exceed one")
        if not self.ring_radius < self.annulus_inner <= self.annulus_outer:
            raise ValueError("bridge requires ring_radius < annulus_inner <= annulus_outer")
        if self.min_declining_sectors > 8:
            raise ValueError("bridge min_declining_sectors must not exceed eight")

    def identity(self) -> dict[str, Any]:
        return {"algorithm_id": ALGORITHM_ID, "algorithm_version": ALGORITHM_VERSION,
                "method": "boundary_median", "profile": asdict(self)}


@dataclass(frozen=True, slots=True)
class BridgeDiagnostics:
    enabled: bool
    identity: dict[str, Any]
    candidate_clusters: int
    accepted_clusters: int
    estimated_samples: int
    rejection_counts: dict[str, int]
    elapsed_seconds: float
    estimated_peak_working_bytes: int

    def record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NativePresentation:
    """Keep the observational package distinct from derived resampling inputs.

    This result deliberately is not a FITSPlane with ``valid`` relabeled. A later
    reprojection adapter must explicitly transport support and estimate influence.
    """
    observation: FITSPlane
    values: np.ndarray
    support: np.ndarray
    estimate_mask: np.ndarray
    diagnostics: BridgeDiagnostics


def estimate_bridge_peak_bytes(pixel_count: int, component_count: int) -> int:
    if pixel_count < 0 or component_count < 0:
        raise ValueError("bridge memory counts must be nonnegative")
    return 24 * int(pixel_count) + 256 * (int(component_count) + 1) + 1024**2


def prepare_native_presentation(
    plane: FITSPlane, *, enabled: bool = True, profile: BridgeProfile | None = None,
) -> NativePresentation:
    """Return a separate bounded presentation result without altering ``plane``."""
    if type(enabled) is not bool:
        raise ValueError("bridge enabled must be a boolean")
    selected_profile = profile if profile is not None else BridgeProfile()
    if not isinstance(selected_profile, BridgeProfile):
        raise TypeError("bridge profile must be a BridgeProfile")
    started = perf_counter()
    if plane.data.size == 0:
        raise ValueError(f"bridge plane '{plane.plane_id}' must not be empty")
    if plane.domain != "native_linear":
        raise ValueError(f"bridge plane '{plane.plane_id}' requires native_linear values")
    estimate_mask = np.zeros(plane.data.shape, dtype=bool)
    if not enabled:
        diagnostics = BridgeDiagnostics(
            False, selected_profile.identity(), 0, 0, 0, {}, perf_counter() - started,
            int(estimate_mask.nbytes),
        )
        return NativePresentation(plane, plane.data, plane.valid, estimate_mask, diagnostics)
    try:
        return _prepare(plane, selected_profile, estimate_mask, started)
    except Exception as exc:
        raise RuntimeError(f"bridge preparation failed for plane '{plane.plane_id}': {exc}") from exc


def _prepare(
    plane: FITSPlane, profile: BridgeProfile, estimate_mask: np.ndarray, started: float,
) -> NativePresentation:
    # All candidate and neighbor decisions consult the original observational plane.
    invalid = ~plane.valid | ~np.isfinite(plane.data)
    labels, component_count = ndimage.label(invalid, structure=np.ones((3, 3), dtype=bool), output=np.int32)
    areas = np.bincount(labels.ravel(), minlength=component_count + 1)
    border_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    exterior = np.zeros(component_count + 1, dtype=bool)
    exterior[border_labels] = True
    exterior[0] = False
    boxes = ndimage.find_objects(labels, max_label=component_count)
    values = plane.data.copy()
    support = plane.valid.copy()
    accepted = 0
    estimated = 0
    rejections: dict[str, int] = {}
    for label, box in enumerate(boxes, start=1):
        if box is None:
            raise RuntimeError(f"missing bounding box for component {label}")
        if exterior[label]:
            reason = "exterior"
        elif areas[label] > profile.max_area:
            reason = "area"
        elif max(axis.stop - axis.start for axis in box) > profile.max_extent:
            reason = "extent"
        else:
            reason = _fill_component(plane, profile, labels, label, box, values, support, estimate_mask)
        if reason is not None:
            rejections[reason] = rejections.get(reason, 0) + 1
        else:
            accepted += 1
            estimated += int(areas[label])
    diagnostics = BridgeDiagnostics(
        True, profile.identity(), component_count, accepted, estimated, rejections,
        perf_counter() - started, estimate_bridge_peak_bytes(plane.data.size, component_count),
    )
    return NativePresentation(plane, values, support, estimate_mask, diagnostics)


def _fill_component(
    plane: FITSPlane, profile: BridgeProfile, labels: np.ndarray, label: int,
    box: tuple[slice, slice], values: np.ndarray, support: np.ndarray, estimate_mask: np.ndarray,
) -> str | None:
    radius = profile.annulus_outer
    if any(axis.start < radius or axis.stop + radius > size for axis, size in zip(box, plane.data.shape)):
        return "edge_patch"
    patch = tuple(slice(axis.start - radius, axis.stop + radius) for axis in box)
    local_component = labels[patch] == label
    data = np.asarray(plane.data[patch], dtype=np.float64)
    observed = plane.valid[patch] & np.isfinite(data)
    ring = ndimage.binary_dilation(
        local_component, structure=np.ones((3, 3), dtype=bool), iterations=profile.ring_radius,
    ) & ~local_component
    yy, xx = np.indices(data.shape)
    height, width = (axis.stop - axis.start for axis in box)
    y0 = x0 = radius
    y1, x1 = radius + height - 1, radius + width - 1
    distance = np.maximum.reduce((y0 - yy, yy - y1, x0 - xx, xx - x1, np.zeros_like(yy)))
    annulus = (distance >= profile.annulus_inner) & (distance <= profile.annulus_outer)
    observed_ring, observed_annulus = ring & observed, annulus & observed
    if not _has_support(observed_ring, ring, profile.min_ring_samples, profile.min_ring_fraction):
        return "ring_support"
    if not _has_support(observed_annulus, annulus, profile.min_annulus_samples, profile.min_annulus_fraction):
        return "annulus_support"
    ring_values, annulus_values = data[observed_ring], data[observed_annulus]
    background = float(np.median(annulus_values))
    noise = float(1.4826 * np.median(np.abs(annulus_values - background)))
    if not np.isfinite(noise) or noise <= 0:
        return "degenerate_noise"
    if np.percentile(ring_values, 25, method="linear") <= background + profile.bright_sigma * noise:
        return "brightness"
    center_y, center_x = (y0 + y1) / 2, (x0 + x1) / 2
    sectors = np.floor(
        ((np.arctan2(yy - center_y, xx - center_x) + np.pi / 8) % (2 * np.pi)) / (np.pi / 4)
    ).astype(np.int8)
    declining = 0
    for sector in range(8):
        ring_sector = data[observed_ring & (sectors == sector)]
        annulus_sector = data[observed_annulus & (sectors == sector)]
        if ring_sector.size < profile.min_sector_ring_samples or annulus_sector.size < profile.min_sector_annulus_samples:
            continue
        if np.median(ring_sector) > np.median(annulus_sector) + profile.sector_sigma * noise:
            declining += 1
    if declining < profile.min_declining_sectors:
        return "sectors"
    fill = np.asarray(np.median(ring_values), dtype=values.dtype)
    if not np.isfinite(fill):
        raise ArithmeticError("nonfinite boundary-median estimate")
    values[patch][local_component] = fill
    support[patch][local_component] = True
    estimate_mask[patch][local_component] = True
    return None


def _has_support(observed: np.ndarray, geometric: np.ndarray, minimum: int, fraction: float) -> bool:
    count = int(np.count_nonzero(observed))
    return count >= minimum and count >= fraction * int(np.count_nonzero(geometric))

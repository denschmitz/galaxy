from __future__ import annotations

import colorsys
from dataclasses import dataclass
import re

import numpy as np

from galaxy.config import MappingConfig, PlaneMappingConfig, RGBMixConfig, DerivedPlaneConfig


CHANNEL_NAMES = ("red", "green", "blue")
WAVELENGTH_HINTS = {
    "F090W": 0.90,
    "F140M": 1.40,
    "F200W": 2.00,
    "F300M": 3.00,
    "F356W": 3.56,
    "F444W": 4.44,
    "F502N": 0.502,
    "F606W": 0.606,
    "F657N": 0.657,
    "F673N": 0.673,
    "F814W": 0.814,
}
FILTER_PATTERN = re.compile(r"^F(?P<value>\d{3,4})(?P<band>[A-Z0-9]+)$")


@dataclass(slots=True)
class CompositionInputs:
    planes: dict[str, np.ndarray]
    metadata: dict[str, dict[str, object]]


def compute_derived_planes(planes: dict[str, np.ndarray], definitions: list[DerivedPlaneConfig]) -> dict[str, np.ndarray]:
    derived: dict[str, np.ndarray] = {}
    for definition in definitions:
        if definition.operation == "linear_combination":
            image = sum(_weighted_plane(planes, term.plane, term.weight) for term in definition.terms)
        else:
            numerator = sum(_weighted_plane(planes, term.plane, term.weight) for term in definition.numerator)
            denominator = sum(_weighted_plane(planes, term.plane, term.weight) for term in definition.denominator)
            image = numerator / (denominator + definition.epsilon)
        derived[definition.name] = image.astype(np.float32)
    return derived


def default_plane_mappings(metadata: dict[str, dict[str, object]], strategy: str = "continuum") -> list[PlaneMappingConfig]:
    sortable: list[tuple[float, str]] = []
    for plane_name, plane_meta in metadata.items():
        filter_name = str(plane_meta.get("filter") or "").upper()
        sortable.append((_filter_wavelength_hint(filter_name), plane_name))
    ordered = [name for _, name in sorted(sortable)]
    if not ordered:
        return []

    mappings: list[PlaneMappingConfig] = []
    last_index = max(len(ordered) - 1, 1)
    for index, plane_name in enumerate(ordered):
        rgb = _continuum_rgb(index / last_index if len(ordered) > 1 else 0.5)
        mappings.append(PlaneMappingConfig(plane=plane_name, rgb=rgb))
    return mappings


def compose_channels(inputs: CompositionInputs, config: MappingConfig, enabled_planes: set[str] | None = None) -> dict[str, np.ndarray]:
    all_planes = dict(inputs.planes)
    all_planes.update(compute_derived_planes(all_planes, config.derived_planes))

    mappings = config.planes or default_plane_mappings(inputs.metadata, config.defaults.strategy)
    first = next(iter(all_planes.values()))
    composed: dict[str, np.ndarray] = {
        channel_name: np.zeros_like(first, dtype=np.float32)
        for channel_name in CHANNEL_NAMES
    }
    for mapping in mappings:
        for plane_name in _resolve_mapping_targets(mapping, all_planes, inputs.metadata):
            if enabled_planes is not None and plane_name in inputs.planes and plane_name not in enabled_planes:
                continue
            for channel_name in CHANNEL_NAMES:
                weight = getattr(mapping.rgb, channel_name)
                if weight == 0:
                    continue
                composed[channel_name] += _weighted_plane(all_planes, plane_name, weight)
    return composed


def _resolve_mapping_targets(
    mapping: PlaneMappingConfig,
    planes: dict[str, np.ndarray],
    metadata: dict[str, dict[str, object]],
) -> list[str]:
    if mapping.plane:
        if mapping.plane not in planes:
            raise KeyError(f"mapping references missing plane '{mapping.plane}'")
        return [mapping.plane]
    filter_name = str(mapping.filter or "").upper()
    matched = [
        plane_name
        for plane_name, plane_meta in metadata.items()
        if str(plane_meta.get("filter") or "").upper() == filter_name and plane_name in planes
    ]
    if not matched:
        raise KeyError(f"mapping references missing filter '{filter_name}'")
    return matched


def _weighted_plane(planes: dict[str, np.ndarray], plane_name: str, weight: float) -> np.ndarray:
    return np.asarray(planes[plane_name], dtype=np.float32) * weight


def _filter_wavelength_hint(filter_name: str) -> float:
    if filter_name in WAVELENGTH_HINTS:
        return WAVELENGTH_HINTS[filter_name]
    match = FILTER_PATTERN.match(filter_name)
    if not match:
        return 999.0
    raw = int(match.group("value"))
    if raw >= 1000:
        return raw / 1000.0
    if raw >= 600:
        return raw / 1000.0
    return raw / 100.0


def _continuum_rgb(position: float) -> RGBMixConfig:
    hue = (1.0 - max(0.0, min(1.0, position))) * (2.0 / 3.0)
    red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return RGBMixConfig(red=float(red), green=float(green), blue=float(blue))

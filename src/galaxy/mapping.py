from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from galaxy.config import ChannelContribution, DerivedPlaneConfig, MappingConfig


CHANNEL_NAMES = ("red", "green", "blue")
WAVELENGTH_HINTS = {
    "F090W": 0.9,
    "F200W": 2.0,
    "F356W": 3.56,
    "F444W": 4.44,
    "F606W": 0.606,
    "F814W": 0.814,
}


@dataclass(slots=True)
class CompositionInputs:
    planes: dict[str, np.ndarray]
    metadata: dict[str, dict[str, object]]


def compute_derived_planes(planes: dict[str, np.ndarray], definitions: list[DerivedPlaneConfig]) -> dict[str, np.ndarray]:
    derived: dict[str, np.ndarray] = {}
    for definition in definitions:
        if definition.operation == "linear_combination":
            image = sum(_weighted_plane(planes, term) for term in definition.terms)
        else:
            numerator = sum(_weighted_plane(planes, term) for term in definition.numerator)
            denominator = sum(_weighted_plane(planes, term) for term in definition.denominator)
            image = numerator / (denominator + definition.epsilon)
        derived[definition.name] = image.astype(np.float32)
    return derived


def default_mapping(metadata: dict[str, dict[str, object]]) -> dict[str, list[ChannelContribution]]:
    sortable = []
    for plane_name, plane_meta in metadata.items():
        filter_name = str(plane_meta.get("filter") or "").upper()
        sortable.append((WAVELENGTH_HINTS.get(filter_name, 999.0), plane_name))
    ordered = [name for _, name in sorted(sortable)]
    if not ordered:
        return {"red": [], "green": [], "blue": []}
    thirds = np.array_split(np.array(ordered, dtype=object), 3)
    return {
        "blue": [ChannelContribution(plane=str(name), weight=1.0) for name in thirds[0].tolist()],
        "green": [ChannelContribution(plane=str(name), weight=1.0) for name in thirds[1].tolist()],
        "red": [ChannelContribution(plane=str(name), weight=1.0) for name in thirds[2].tolist()],
    }


def compose_channels(inputs: CompositionInputs, config: MappingConfig, enabled_planes: set[str] | None = None) -> dict[str, np.ndarray]:
    all_planes = dict(inputs.planes)
    all_planes.update(compute_derived_planes(all_planes, config.derived_planes))

    channels = config.channels
    if not any(channels[name] for name in CHANNEL_NAMES):
        channels = default_mapping(inputs.metadata)

    composed: dict[str, np.ndarray] = {}
    for channel_name in CHANNEL_NAMES:
        image = None
        for contribution in channels[channel_name]:
            if enabled_planes is not None and contribution.plane in inputs.planes and contribution.plane not in enabled_planes:
                continue
            term = _weighted_plane(all_planes, contribution)
            image = term if image is None else image + term
        if image is None:
            first = next(iter(all_planes.values()))
            image = np.zeros_like(first, dtype=np.float32)
        composed[channel_name] = image.astype(np.float32)
    return composed


def _weighted_plane(planes: dict[str, np.ndarray], contribution: ChannelContribution) -> np.ndarray:
    return np.asarray(planes[contribution.plane], dtype=np.float32) * contribution.weight

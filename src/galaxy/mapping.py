from __future__ import annotations

import colorsys
from dataclasses import dataclass
import re

import numpy as np

from galaxy.processing_config import (
    DerivedPlaneConfig,
    MappingConfig,
    PlaneMappingConfig,
    PlaneNormalizationConfig,
    PlaneContributionConfig,
    RGBMixConfig,
)
from galaxy.reprojection import ReprojectedPlane


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
    planes: dict[str, ReprojectedPlane]

    def __post_init__(self) -> None:
        if not self.planes:
            raise ValueError("composition requires at least one image package")
        for name, plane in self.planes.items():
            if name != plane.plane_id:
                raise ValueError(f"composition key '{name}' does not match plane ID '{plane.plane_id}'")
            if plane.domain != "aligned_linear":
                raise ValueError(f"plane '{name}' has unsupported composition domain '{plane.domain}'")


@dataclass(slots=True)
class CompositionResult:
    channels: dict[str, np.ndarray]
    channel_coverage: dict[str, np.ndarray]
    plane_diagnostics: dict[str, dict[str, object]]
    warnings: list[str]
    required_support: np.ndarray
    required_plane_ids: tuple[str, ...]
    required_source_ids: tuple[str, ...]
    channel_statistics: dict[str, np.ndarray] | None = None
    required_statistics_support: np.ndarray | None = None


@dataclass(slots=True)
class NormalizationResult:
    plane: ReprojectedPlane
    diagnostics: dict[str, object]

    def __post_init__(self) -> None:
        if self.plane.domain != "display_plane":
            raise ValueError("normalization result must use the display_plane domain")


@dataclass(slots=True)
class RGBContribution:
    plane: ReprojectedPlane
    weights: RGBMixConfig


@dataclass(slots=True)
class RGBMixResult:
    channels: dict[str, np.ndarray]
    channel_coverage: dict[str, np.ndarray]
    plane_signal: dict[str, dict[str, float]]
    channel_statistics: dict[str, np.ndarray]


def compute_derived_planes(
    planes: dict[str, ReprojectedPlane],
    definitions: list[DerivedPlaneConfig],
) -> dict[str, ReprojectedPlane]:
    available = dict(planes)
    derived: dict[str, ReprojectedPlane] = {}
    for definition in definitions:
        if definition.name in available:
            raise ValueError(f"derived plane name already exists: '{definition.name}'")
        if definition.operation == "linear_combination":
            image, valid, coverage, parents, presentation, influence = _weighted_sum(available, definition.terms)
            unit = _compatible_unit(available, [term.plane for term in definition.terms if term.weight != 0])
        else:
            numerator, numerator_valid, numerator_coverage, numerator_parents, numerator_presentation, numerator_influence = _weighted_sum(
                available, definition.numerator
            )
            denominator, denominator_valid, denominator_coverage, denominator_parents, denominator_presentation, denominator_influence = _weighted_sum(
                available, definition.denominator
            )
            numerator_unit = _compatible_unit(
                available, [term.plane for term in definition.numerator if term.weight != 0]
            )
            denominator_unit = _compatible_unit(
                available, [term.plane for term in definition.denominator if term.weight != 0]
            )
            if numerator_unit != denominator_unit:
                raise ValueError(
                    f"derived ratio '{definition.name}' requires compatible numerator and denominator units"
                )
            valid = numerator_valid & denominator_valid & (np.abs(denominator) > definition.epsilon)
            coverage = np.minimum(numerator_coverage, denominator_coverage)
            image = np.zeros_like(numerator, dtype=np.float32)
            presentation = np.minimum(numerator_presentation, denominator_presentation)
            usable = (presentation > 0) & (np.abs(denominator) > definition.epsilon)
            presentation = np.where(usable, presentation, 0)
            image[usable] = numerator[usable] / denominator[usable]
            influence = (numerator_influence | denominator_influence) & usable
            parents = tuple(dict.fromkeys((*numerator_parents, *denominator_parents)))
            unit = "dimensionless" if numerator_unit is not None else None
        first = available[parents[0]]
        metadata = {
            "native_unit": unit,
            "artifact_branch": first.branch,
            "derived_operation": definition.operation,
        }
        package = ReprojectedPlane(
            plane_id=definition.name,
            data=image.astype(np.float32),
            footprint=coverage.astype(np.float32),
            metadata=metadata,
            wcs=None if first.wcs is None else first.wcs.deepcopy(),
            valid=valid, presentation_support=presentation, estimate_influence=influence,
            domain="aligned_linear",
            branch=first.branch,
            source_ids=tuple(dict.fromkeys(source for parent in parents for source in available[parent].source_ids)),
            parent_ids=parents,
            grid_id=first.grid_id,
        )
        derived[definition.name] = package
        available[definition.name] = package
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
    return compose_channels_with_diagnostics(inputs, config, enabled_planes).channels


def compose_channels_with_diagnostics(
    inputs: CompositionInputs,
    config: MappingConfig,
    enabled_planes: set[str] | None = None,
    *,
    black_reference_policy: str = "legacy_percentile",
) -> CompositionResult:
    all_planes = dict(inputs.planes)
    all_planes.update(compute_derived_planes(all_planes, config.derived_planes))

    metadata = {name: package.metadata for name, package in all_planes.items()}
    mappings = config.planes or default_plane_mappings(metadata, config.defaults.strategy)
    reference = next(iter(all_planes.values()))
    diagnostics: dict[str, dict[str, object]] = {}
    contributions: list[RGBContribution] = []
    normalized_cache: dict[tuple[str, str], NormalizationResult] = {}
    mapped_units: set[str] = set()
    uses_native = False
    for mapping in mappings:
        if not any(getattr(mapping.rgb, channel) != 0 for channel in CHANNEL_NAMES):
            continue
        for plane_name in _resolve_mapping_targets(mapping, all_planes, metadata):
            if enabled_planes is not None and plane_name in inputs.planes and plane_name not in enabled_planes:
                continue
            policy = mapping.normalization or config.defaults.normalization
            cache_key = (plane_name, policy.model_dump_json())
            if cache_key not in normalized_cache:
                normalized_cache[cache_key] = normalize_plane_for_display(
                    all_planes[plane_name], policy,
                    black_reference_policy=black_reference_policy,
                )
            normalized = normalized_cache[cache_key]
            plane_diagnostic = normalized.diagnostics
            diagnostics[plane_name] = plane_diagnostic
            unit = str(plane_diagnostic.get("native_unit") or "").strip()
            if unit:
                mapped_units.add(unit.casefold())
            uses_native = uses_native or policy.mode == "native"
            contributions.append(RGBContribution(normalized.plane, mapping.rgb))

    if not contributions:
        raise ValueError("composition requires at least one enabled nonzero RGB contribution")
    mixed = mix_display_planes(reference, contributions)
    required_by_id = {item.plane.plane_id: item.plane for item in contributions}
    required_support = np.logical_and.reduce([
        plane.presentation_valid for plane in required_by_id.values()
    ])
    required_statistics_support = np.logical_and.reduce([plane.statistics_valid for plane in required_by_id.values()])
    required_source_ids = tuple(dict.fromkeys(
        source_id
        for plane in required_by_id.values()
        for source_id in plane.source_ids
    ))
    channel_signal = mixed.plane_signal

    totals = {
        channel: sum(values[channel] for values in channel_signal.values())
        for channel in CHANNEL_NAMES
    }
    for plane_name, diagnostic in diagnostics.items():
        values = channel_signal.get(plane_name, {})
        diagnostic["rgb_contribution_percent"] = {
            channel: (100.0 * values.get(channel, 0.0) / totals[channel] if totals[channel] > 0 else 0.0)
            for channel in CHANNEL_NAMES
        }
    warnings: list[str] = []
    if len(mapped_units) > 1 and uses_native:
        warnings.append(
            "Mixed native FITS units are mapped while native normalization is enabled; "
            "some planes may be visually suppressed."
        )
    return CompositionResult(
        mixed.channels, mixed.channel_coverage, diagnostics, warnings,
        required_support, tuple(required_by_id), required_source_ids,
        mixed.channel_statistics, required_statistics_support,
    )


def normalize_plane_for_display(
    plane: ReprojectedPlane,
    policy: PlaneNormalizationConfig,
    *,
    black_reference_policy: str = "legacy_percentile",
) -> NormalizationResult:
    if plane.domain != "aligned_linear":
        raise ValueError(
            f"plane '{plane.plane_id}' has unsupported normalization domain '{plane.domain}'"
        )
    plane_name = plane.plane_id
    image = np.asarray(plane.data, dtype=np.float32)
    observed = plane.statistics_valid
    valid = plane.presentation_valid
    if not np.any(observed):
        raise ValueError(f"plane '{plane_name}' has no finite valid pixels for display normalization")
    black_point: float | None = None
    white_point: float | None = None
    if policy.reference is not None:
        reference = policy.reference
        stale = (
            reference.branch != plane.branch
            or reference.grid_id != plane.grid_id
            or tuple(reference.source_ids) != tuple(plane.source_ids)
            or reference.unit != plane.unit
        )
        if stale:
            raise ValueError(
                f"plane '{plane_name}' has a stale normalization reference identity"
            )
    if policy.mode in {"percentile", "fixed_bounds"}:
        values = image[observed]
        if policy.mode == "fixed_bounds":
            black_point = float(policy.black_value)
            white_point = float(policy.white_value)
        else:
            black_point = (
                0.0 if black_reference_policy == "corrected_zero"
                else float(np.percentile(values, policy.black_percentile))
            )
            white_point = float(np.percentile(values, policy.white_percentile))
        if white_point <= black_point:
            white_point = black_point + 1e-6
        display = np.zeros_like(image, dtype=np.float32)
        display[valid] = np.clip(
            (image[valid] - black_point) / (white_point - black_point), 0.0, 1.0
        )
        if policy.stretch == "asinh":
            display[valid] = np.arcsinh(display[valid] * policy.stretch_parameter) / np.arcsinh(
                policy.stretch_parameter
            )
        elif policy.stretch == "gamma":
            display[valid] = np.power(display[valid], 1.0 / policy.stretch_parameter)
    else:
        display = np.where(valid, image, 0.0).astype(np.float32)
    display *= policy.gain
    diagnostic: dict[str, object] = {
        "plane_id": plane_name,
        "native_unit": plane.unit,
        "mask_sources": list(plane.metadata.get("mask_sources") or []),
        "normalization_mode": policy.mode,
        "black_percentile": policy.black_percentile if policy.mode == "percentile" else None,
        "white_percentile": policy.white_percentile if policy.mode == "percentile" else None,
        "black_point": black_point,
        "black_reference_policy": black_reference_policy,
        "white_point": white_point,
        "normalization_reference_id": (
            policy.reference.reference_id if policy.reference is not None else None
        ),
        "gain": policy.gain,
        "valid_coverage_fraction": float(np.count_nonzero(valid) / valid.size),
    }
    metadata = dict(plane.metadata)
    metadata["source_native_unit"] = plane.unit
    metadata["native_unit"] = "unitless"
    metadata["normalization_mode"] = policy.mode
    normalized = ReprojectedPlane(
        plane_id=plane_name,
        data=display,
        footprint=np.asarray(plane.coverage, dtype=np.float32).copy(),
        metadata=metadata,
        wcs=plane.wcs.deepcopy() if plane.wcs is not None else None,
        valid=plane.valid.copy(),
        presentation_support=plane.presentation_support.copy(),
        estimate_influence=plane.estimate_influence.copy(),
        domain="display_plane",
        branch=plane.branch,
        source_ids=plane.source_ids,
        parent_ids=(plane.plane_id,),
        grid_id=plane.grid_id,
    )
    return NormalizationResult(normalized, diagnostic)


def mix_display_planes(
    reference: ReprojectedPlane,
    contributions: list[RGBContribution],
) -> RGBMixResult:
    if reference.domain != "aligned_linear":
        raise ValueError("RGB mixing reference must use the aligned_linear domain")
    channels = {
        channel_name: np.zeros_like(reference.data, dtype=np.float32)
        for channel_name in CHANNEL_NAMES
    }
    channel_coverage = {
        channel_name: np.zeros_like(reference.data, dtype=bool)
        for channel_name in CHANNEL_NAMES
    }
    channel_influence = {key: np.zeros_like(reference.data, dtype=bool) for key in CHANNEL_NAMES}
    plane_signal: dict[str, dict[str, float]] = {}
    for contribution in contributions:
        plane = contribution.plane
        if plane.domain != "display_plane":
            raise ValueError(f"plane '{plane.plane_id}' has unsupported RGB-mixing domain '{plane.domain}'")
        if plane.data.shape != reference.data.shape or plane.grid_id != reference.grid_id:
            raise ValueError("RGB mixing requires display planes on the reference grid")
        valid = plane.presentation_valid
        signal = plane_signal.setdefault(plane.plane_id, {name: 0.0 for name in CHANNEL_NAMES})
        for channel_name in CHANNEL_NAMES:
            weight = getattr(contribution.weights, channel_name)
            if weight == 0:
                continue
            weighted = np.asarray(plane.data, dtype=np.float32) * weight
            channels[channel_name] += weighted
            channel_coverage[channel_name] |= valid
            channel_influence[channel_name] |= plane.estimate_influence
            signal[channel_name] += float(np.sum(np.abs(weighted[valid]), dtype=np.float64))
    return RGBMixResult(channels, channel_coverage, plane_signal,
                        {key: channel_coverage[key] & ~channel_influence[key] for key in CHANNEL_NAMES})


def _resolve_mapping_targets(
    mapping: PlaneMappingConfig,
    planes: dict[str, ReprojectedPlane],
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


def _weighted_sum(
    planes: dict[str, ReprojectedPlane],
    terms: list[PlaneContributionConfig],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...], np.ndarray, np.ndarray]:
    active = [term for term in terms if term.weight != 0]
    if not active:
        raise ValueError("derived arithmetic requires at least one nonzero-weight operand")
    packages: list[ReprojectedPlane] = []
    for term in active:
        if term.plane not in planes:
            raise KeyError(f"derived arithmetic references missing plane '{term.plane}'")
        packages.append(planes[term.plane])
    reference = packages[0]
    for package in packages[1:]:
        if package.data.shape != reference.data.shape or package.grid_id != reference.grid_id:
            raise ValueError("derived arithmetic requires operands on the same grid")
        if package.branch != reference.branch:
            raise ValueError("derived arithmetic requires operands from the same branch")
    valid = np.logical_and.reduce([np.asarray(package.valid, dtype=bool) for package in packages])
    coverage = np.minimum.reduce([np.asarray(package.coverage, dtype=np.float32) for package in packages])
    presentation = np.minimum.reduce([package.presentation_support for package in packages])
    usable = np.logical_and.reduce([package.presentation_valid for package in packages])
    influence = np.logical_or.reduce([package.estimate_influence for package in packages]) & usable
    result = np.zeros_like(reference.data, dtype=np.float32)
    for term, package in zip(active, packages, strict=True):
        result[usable] += np.asarray(package.data, dtype=np.float32)[usable] * term.weight
    return result, valid, coverage, tuple(term.plane for term in active), presentation, influence


def _compatible_unit(planes: dict[str, ReprojectedPlane], names: list[str]) -> str | None:
    if any(planes[name].unit is None for name in names):
        return None
    units = {planes[name].unit for name in names if planes[name].unit is not None}
    if len(units) > 1:
        raise ValueError("derived linear arithmetic requires compatible operand units")
    return next(iter(units), None)


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

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from galaxy.processing_config import AutoStretchResolutionConfig, StretchConfig, ToneConfig


SHARED_INTENSITY_EPSILON = 1e-12
AUTOSTRETCH_ALGORITHM_VERSION = "autostretch-shared-asinh-v1"


@dataclass(frozen=True, slots=True)
class PreparedTone:
    rgb: np.ndarray
    masks: np.ndarray


def prepare_tone(
    channels: dict[str, np.ndarray],
    tone: ToneConfig,
    *,
    valid_masks: dict[str, np.ndarray] | None = None,
    statistics_masks: dict[str, np.ndarray] | None = None,
    black_reference_policy: str = "legacy_percentile",
) -> PreparedTone:
    """Resolve output-channel bounds without applying a main tone curve."""
    normalized_channels: list[np.ndarray] = []
    channel_masks: list[np.ndarray] = []
    for channel_name in ("red", "green", "blue"):
        image = np.asarray(channels[channel_name], dtype=np.float64)
        valid = np.isfinite(image)
        if valid_masks is not None:
            valid &= np.asarray(valid_masks[channel_name], dtype=bool)
        if not np.any(valid):
            raise ValueError(f"output channel '{channel_name}' has no finite valid pixels")
        statistics_valid = np.isfinite(image)
        if statistics_masks is not None:
            statistics_valid &= np.asarray(statistics_masks[channel_name], dtype=bool)
        else:
            statistics_valid &= valid
        if not np.any(statistics_valid):
            raise ValueError(f"output channel '{channel_name}' has no finite reference pixels")
        values = image[statistics_valid]
        black = (
            0.0 if black_reference_policy == "corrected_zero"
            else float(np.percentile(values, tone.percentiles.black))
        )
        white = float(np.percentile(values, tone.percentiles.white))
        if white <= black:
            white = black + 1e-6
        normalized = np.zeros_like(image, dtype=np.float64)
        normalized[valid] = np.clip((image[valid] - black) / (white - black), 0.0, 1.0)
        normalized_channels.append(normalized)
        channel_masks.append(valid)
    return PreparedTone(
        np.stack(normalized_channels, axis=-1),
        np.stack(channel_masks, axis=-1),
    )


def apply_tone(
    channels: dict[str, np.ndarray],
    tone: ToneConfig,
    bit_depth: int = 16,
    valid_masks: dict[str, np.ndarray] | None = None,
    statistics_masks: dict[str, np.ndarray] | None = None,
    black_reference_policy: str = "legacy_percentile",
) -> np.ndarray:
    prepared = prepare_tone(
        channels,
        tone,
        valid_masks=valid_masks,
        statistics_masks=statistics_masks,
        black_reference_policy=black_reference_policy,
    )
    rgb = prepared.rgb
    if tone.application == "per_channel":
        output = np.zeros_like(rgb, dtype=np.float64)
        stretch_set = tone.stretch.model_dump()
        for index, channel_name in enumerate(("red", "green", "blue")):
            channel = _apply_stretch(rgb[..., index], stretch_set[channel_name])
            channel = channel * getattr(tone.gain, channel_name) + getattr(tone.bias, channel_name)
            output[..., index] = channel
        output = np.clip(output, 0.0, 1.0)
    else:
        assert tone.shared_stretch is not None
        adjusted = np.empty_like(rgb, dtype=np.float64)
        for index, channel_name in enumerate(("red", "green", "blue")):
            adjusted[..., index] = (
                rgb[..., index] * getattr(tone.gain, channel_name)
                + getattr(tone.bias, channel_name)
            )
        if np.any(prepared.masks & (adjusted < 0.0)):
            raise ValueError("shared-intensity tone does not accept supported negative RGB")
        output = apply_shared_intensity(
            adjusted, tone.shared_stretch, prepared.masks, tone.gamut_policy
        )
    output = _apply_saturation(output, tone.saturation)
    output[~prepared.masks] = 0.0
    max_value = float((1 << bit_depth) - 1)
    return np.clip(output, 0.0, 1.0) * max_value


def apply_shared_intensity(
    rgb: np.ndarray,
    stretch: StretchConfig,
    masks: np.ndarray | None = None,
    gamut_policy: str = "clip",
) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64)
    if values.ndim < 1 or values.shape[-1] != 3:
        raise ValueError("shared-intensity tone requires an RGB array")
    valid = np.isfinite(values) if masks is None else np.asarray(masks, dtype=bool) & np.isfinite(values)
    if valid.shape != values.shape:
        raise ValueError("shared-intensity masks must match RGB shape")
    if np.any(valid & (values < 0.0)):
        raise ValueError("shared-intensity tone does not accept supported negative RGB")
    working = np.where(valid, values, 0.0)
    output = _shared_pre_gamut(working, stretch, valid)
    if gamut_policy == "rescale":
        maximum = np.max(output, axis=-1)
        scale = np.ones_like(maximum)
        over = maximum > 1.0
        scale[over] = 1.0 / maximum[over]
        output *= scale[..., None]
    elif gamut_policy == "clip":
        output = np.clip(output, 0.0, 1.0)
    else:
        raise ValueError(f"unsupported gamut policy: {gamut_policy}")
    output[~valid] = 0.0
    return output


def propose_auto_stretch(
    linear_rgb: np.ndarray,
    sample_mask: np.ndarray,
    *,
    reference_id: str,
    branch: str,
    grid_id: str,
    source_ids: list[str],
    minimum_samples: int = 256,
) -> AutoStretchResolutionConfig:
    values = np.asarray(linear_rgb, dtype=np.float64)
    if values.ndim != 3 or values.shape[-1] != 3:
        raise ValueError("auto-stretch requires an RGB image")
    mask = np.asarray(sample_mask, dtype=bool)
    if mask.shape != values.shape[:2]:
        raise ValueError("auto-stretch sample mask must match RGB dimensions")
    selected = mask & np.all(np.isfinite(values), axis=-1)
    required = max(256, int(minimum_samples))
    count = int(np.count_nonzero(selected))
    if count < required:
        raise ValueError(f"auto-stretch sample count {count} is below minimum {required}")
    intensity = np.mean(values, axis=-1)
    sample = intensity[selected]
    median = float(np.median(sample))
    spread = float(1.4826 * np.median(np.abs(sample - median)))
    if spread <= SHARED_INTENSITY_EPSILON:
        raise ValueError("auto-stretch reference sample is constant")
    if median <= SHARED_INTENSITY_EPSILON:
        raise ValueError("auto-stretch reference median must be positive")
    target = 0.1
    if median >= target:
        raise ValueError("auto-stretch reference median is already at or above target 0.1")
    object_fraction = float(np.count_nonzero(sample > median + 3.0 * spread) / count)
    if object_fraction > 0.25:
        raise ValueError("auto-stretch reference sample is object-dominated")
    parameter = _solve_asinh_parameter(median, target)
    stretch = StretchConfig(kind="asinh", parameter=parameter)
    valid_channels = np.isfinite(values)
    pre_gamut = _shared_pre_gamut(values, stretch, valid_channels)
    supported = pre_gamut[valid_channels]
    return AutoStretchResolutionConfig(
        reference_id=reference_id,
        branch=branch,
        grid_id=grid_id,
        source_ids=source_ids,
        sample_count=count,
        source_median=median,
        robust_spread=spread,
        object_fraction=object_fraction,
        resolved_parameter=parameter,
        low_clipping_fraction=float(np.count_nonzero(supported < 0.0) / supported.size),
        high_clipping_fraction=float(np.count_nonzero(supported > 1.0) / supported.size),
        confidence="high" if count >= 4096 and object_fraction <= 0.05 else "qualified",
    )


def _shared_pre_gamut(
    rgb: np.ndarray, stretch: StretchConfig, masks: np.ndarray,
) -> np.ndarray:
    working = np.where(masks, np.asarray(rgb, dtype=np.float64), 0.0)
    intensity = np.mean(working, axis=-1)
    transformed = _apply_stretch(intensity, stretch.model_dump())
    multiplier = np.zeros_like(intensity)
    positive = intensity > SHARED_INTENSITY_EPSILON
    multiplier[positive] = transformed[positive] / intensity[positive]
    return working * multiplier[..., None]


def _solve_asinh_parameter(source: float, target: float) -> float:
    def value(parameter: float) -> float:
        return float(np.arcsinh(parameter * source) / np.arcsinh(parameter))

    low, high = 1e-6, 1e6
    if not (value(low) <= target <= value(high)):
        raise ValueError("auto-stretch target cannot be reached by bounded asinh")
    for _ in range(80):
        middle = (low + high) / 2.0
        if value(middle) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _apply_stretch(image: np.ndarray, stretch: dict[str, float | str | None]) -> np.ndarray:
    kind = stretch["kind"]
    values = np.asarray(image, dtype=np.float64)
    if kind == "linear":
        return values.copy()
    if kind == "gamma":
        return np.power(values, 1.0 / float(stretch["parameter"]))
    if kind == "asinh":
        parameter = float(stretch["parameter"])
        return np.arcsinh(values * parameter) / np.arcsinh(parameter)
    if kind == "ghs":
        return generalized_hyperbolic_stretch(
            values,
            stretch_factor=float(stretch["stretch_factor"]),
            local_intensity=float(stretch["local_intensity"]),
            symmetry_point=float(stretch["symmetry_point"]),
            shadow_protection=float(stretch["shadow_protection"]),
            highlight_protection=float(stretch["highlight_protection"]),
        )
    raise ValueError(f"unsupported stretch kind: {kind}")


def generalized_hyperbolic_stretch(
    image: np.ndarray,
    *,
    stretch_factor: float,
    local_intensity: float,
    symmetry_point: float,
    shadow_protection: float,
    highlight_protection: float,
) -> np.ndarray:
    """Forward GHS v3.0.4 transform, independently implemented from its equations."""
    if not 0.0 <= stretch_factor <= 20.0:
        raise ValueError("GHS stretch_factor must be in [0,20]")
    if not -5.0 <= local_intensity <= 15.0:
        raise ValueError("GHS local_intensity must be in [-5,15]")
    if not 0.0 <= shadow_protection <= symmetry_point <= highlight_protection <= 1.0:
        raise ValueError("GHS requires 0 <= LP <= SP <= HP <= 1")
    values = np.asarray(image, dtype=np.float64)
    if stretch_factor == 0.0:
        return values.copy()
    d_value = float(np.expm1(stretch_factor))
    b_value = float(local_intensity)

    def base(x: np.ndarray) -> np.ndarray:
        if np.isclose(b_value, -1.0, atol=1e-12, rtol=0.0):
            return np.log1p(d_value * x)
        if b_value < 0.0:
            return (1.0 - np.power(
                1.0 - b_value * d_value * x, (b_value + 1.0) / b_value
            )) / (d_value * (b_value + 1.0))
        if np.isclose(b_value, 0.0, atol=1e-12, rtol=0.0):
            return -np.expm1(-d_value * x)
        if np.isclose(b_value, 1.0, atol=1e-12, rtol=0.0):
            return 1.0 - np.power(1.0 + d_value * x, -1.0)
        return 1.0 - np.power(1.0 + b_value * d_value * x, -1.0 / b_value)

    def derivative(x: np.ndarray) -> np.ndarray:
        if np.isclose(b_value, -1.0, atol=1e-12, rtol=0.0):
            return d_value / (1.0 + d_value * x)
        if b_value < 0.0:
            return np.power(1.0 - b_value * d_value * x, 1.0 / b_value)
        if np.isclose(b_value, 0.0, atol=1e-12, rtol=0.0):
            return d_value * np.exp(-d_value * x)
        if np.isclose(b_value, 1.0, atol=1e-12, rtol=0.0):
            return d_value * np.power(1.0 + d_value * x, -2.0)
        return d_value * np.power(
            1.0 + b_value * d_value * x, -(1.0 + b_value) / b_value
        )

    lp, sp, hp = shadow_protection, symmetry_point, highlight_protection
    t2 = lambda x: -base(sp - x)
    t3 = lambda x: base(x - sp)
    t2_lp = float(t2(np.asarray(lp)))
    t2_prime_lp = float(derivative(np.asarray(sp - lp)))
    t3_hp = float(t3(np.asarray(hp)))
    t3_prime_hp = float(derivative(np.asarray(hp - sp)))
    t1_zero = t2_prime_lp * -lp + t2_lp
    t4_one = t3_prime_hp * (1.0 - hp) + t3_hp
    denominator = t4_one - t1_zero
    if not np.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("GHS normalization denominator is not positive and finite")

    raw = np.empty_like(values, dtype=np.float64)
    below_lp = values < lp
    below_sp = (values >= lp) & (values < sp)
    below_hp = (values >= sp) & (values < hp)
    above_hp = values >= hp
    raw[below_lp] = t2_prime_lp * (values[below_lp] - lp) + t2_lp
    raw[below_sp] = t2(values[below_sp])
    raw[below_hp] = t3(values[below_hp])
    raw[above_hp] = t3_prime_hp * (values[above_hp] - hp) + t3_hp
    result = (raw - t1_zero) / denominator
    if not np.all(np.isfinite(result)):
        raise ValueError("GHS produced nonfinite output")
    return result


def _apply_saturation(rgb: np.ndarray, factor: float) -> np.ndarray:
    luminance = rgb.mean(axis=-1, keepdims=True)
    return np.clip(luminance + (rgb - luminance) * factor, 0.0, 1.0)

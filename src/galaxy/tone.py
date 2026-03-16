from __future__ import annotations

import numpy as np

from galaxy.config import ToneConfig


def apply_tone(channels: dict[str, np.ndarray], tone: ToneConfig, bit_depth: int = 16) -> np.ndarray:
    stacked = []
    for channel_name in ("red", "green", "blue"):
        image = np.asarray(channels[channel_name], dtype=np.float32)
        black = np.nanpercentile(image, tone.percentiles.black)
        white = np.nanpercentile(image, tone.percentiles.white)
        if white <= black:
            white = black + 1e-6
        normalized = np.clip((image - black) / (white - black), 0.0, 1.0)
        normalized = _apply_stretch(normalized, tone.stretch.model_dump()[channel_name])
        normalized = normalized * getattr(tone.gain, channel_name) + getattr(tone.bias, channel_name)
        stacked.append(np.clip(normalized, 0.0, 1.0))
    rgb = np.stack(stacked, axis=-1)
    rgb = _apply_saturation(rgb, tone.saturation)
    max_value = float((1 << bit_depth) - 1)
    return np.clip(rgb, 0.0, 1.0) * max_value


def _apply_stretch(image: np.ndarray, stretch: dict[str, float | str]) -> np.ndarray:
    if stretch["kind"] == "gamma":
        return np.power(image, 1.0 / float(stretch["parameter"]))
    return np.arcsinh(image * float(stretch["parameter"])) / np.arcsinh(float(stretch["parameter"]))


def _apply_saturation(rgb: np.ndarray, factor: float) -> np.ndarray:
    luminance = rgb.mean(axis=-1, keepdims=True)
    return np.clip(luminance + (rgb - luminance) * factor, 0.0, 1.0)

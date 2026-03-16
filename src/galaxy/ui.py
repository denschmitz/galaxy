from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import streamlit as st
import yaml

from galaxy.config import ChannelContribution, MappingConfig, MappingDefaults, StretchConfig, ToneConfig, ToneGainBias, TonePercentiles, ToneStretchSet
from galaxy.mapping import CompositionInputs, compose_channels
from galaxy.planes import load_multiplane_fits
from galaxy.tone import apply_tone


def main() -> None:
    st.set_page_config(page_title="Galaxy Preview", layout="wide")
    planes_path = _resolve_planes_path()
    if not planes_path:
        st.error("Provide a multi-plane FITS path as an argument.")
        return

    planes = load_multiplane_fits(planes_path)
    metadata = {name: {"filter": name} for name in planes}

    st.sidebar.header("Planes")
    _style_loader(list(planes.keys()))
    enabled = {name for name in planes if st.sidebar.checkbox(name, key=_enabled_key(name))}

    mapping = _mapping_controls(list(planes.keys()))
    tone = _tone_controls()

    composed = compose_channels(CompositionInputs(planes=planes, metadata=metadata), mapping, enabled)
    rgb = apply_tone(composed, tone, bit_depth=16).astype(np.uint16)
    preview = np.clip(rgb / 257.0, 0, 255).astype(np.uint8)

    st.image(preview, caption="Preview", use_container_width=True)

    state = {
        "mapping": mapping.model_dump(mode="json"),
        "tone": tone.model_dump(mode="json"),
        "enabled_planes": sorted(enabled),
    }
    st.sidebar.download_button("Download style YAML", yaml.safe_dump(state, sort_keys=False), file_name="galaxy-style.yaml")
    st.sidebar.download_button("Download style JSON", json.dumps(state, indent=2), file_name="galaxy-style.json")


def _resolve_planes_path() -> Path | None:
    args = sys.argv[1:]
    for arg in args:
        candidate = Path(arg)
        if candidate.exists():
            return candidate
    return None


def _mapping_controls(plane_names: list[str]) -> MappingConfig:
    channels: dict[str, list[ChannelContribution]] = {"red": [], "green": [], "blue": []}
    st.sidebar.header("RGB Weights")
    for channel in ("red", "green", "blue"):
        st.sidebar.subheader(channel.title())
        for plane_name in plane_names:
            weight_key = _weight_key(channel, plane_name)
            if weight_key not in st.session_state:
                st.session_state[weight_key] = 1.0 if plane_name in _default_channel_members(channel, plane_names) else 0.0
            weight = st.sidebar.slider(
                f"{channel}:{plane_name}",
                min_value=0.0,
                max_value=3.0,
                step=0.05,
                key=weight_key,
            )
            if weight > 0:
                channels[channel].append(ChannelContribution(plane=plane_name, weight=weight))
    return MappingConfig(defaults=MappingDefaults(strategy="wavelength_order"), channels=channels, derived_planes=[])


def _tone_controls() -> ToneConfig:
    st.sidebar.header("Tone")
    _ensure_default("tone:black", 1.0)
    _ensure_default("tone:white", 99.5)
    _ensure_default("tone:saturation", 1.0)
    black = st.sidebar.slider("Black percentile", 0.0, 20.0, 0.0, 0.1, key="tone:black")
    white = st.sidebar.slider("White percentile", 80.0, 100.0, 100.0, 0.1, key="tone:white")
    saturation = st.sidebar.slider("Saturation", 0.0, 3.0, 0.0, 0.05, key="tone:saturation")
    gains = {}
    stretch = {}
    for channel in ("red", "green", "blue"):
        gain_key = f"tone:gain:{channel}"
        stretch_kind_key = f"tone:stretch-kind:{channel}"
        stretch_param_key = f"tone:stretch-parameter:{channel}"
        _ensure_default(gain_key, 1.0)
        _ensure_default(stretch_kind_key, "asinh")
        _ensure_default(stretch_param_key, 4.0)
        gains[channel] = st.sidebar.slider(f"{channel.title()} gain", 0.0, 3.0, 0.0, 0.05, key=gain_key)
        kind = st.sidebar.selectbox(
            f"{channel.title()} stretch",
            ("asinh", "gamma"),
            index=0 if st.session_state[stretch_kind_key] == "asinh" else 1,
            key=stretch_kind_key,
        )
        parameter = st.sidebar.slider(
            f"{channel.title()} stretch parameter",
            0.1,
            10.0,
            0.1,
            0.1,
            key=stretch_param_key,
        )
        stretch[channel] = StretchConfig(kind=kind, parameter=parameter)
    return ToneConfig(
        stretch=ToneStretchSet(**stretch),
        percentiles=TonePercentiles(black=black, white=white),
        gain=ToneGainBias(**gains),
        bias=ToneGainBias(red=0.0, green=0.0, blue=0.0),
        saturation=saturation,
    )


def _default_channel_members(channel: str, plane_names: list[str]) -> set[str]:
    if not plane_names:
        return set()
    thirds = np.array_split(np.array(plane_names, dtype=object), 3)
    return {
        "blue": set(str(item) for item in thirds[0].tolist()),
        "green": set(str(item) for item in thirds[1].tolist()),
        "red": set(str(item) for item in thirds[2].tolist()),
    }[channel]


def _style_loader(plane_names: list[str]) -> None:
    uploaded = st.sidebar.file_uploader("Load style YAML/JSON", type=["yaml", "yml", "json"])
    if not uploaded:
        for plane_name in plane_names:
            _ensure_default(_enabled_key(plane_name), True)
        return

    style_text = uploaded.getvalue().decode("utf-8")
    fingerprint = f"{uploaded.name}:{hash(style_text)}"
    if st.session_state.get("style:fingerprint") == fingerprint:
        return

    style = _parse_style_document(style_text)
    _seed_style_state(style, plane_names)
    st.session_state["style:fingerprint"] = fingerprint


def _parse_style_document(text: str) -> dict[str, Any]:
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError("style document must contain a mapping at the top level")
    return parsed


def _seed_style_state(style: dict[str, Any], plane_names: list[str]) -> None:
    enabled = {str(name) for name in style.get("enabled_planes", [])}
    mapping = style.get("mapping", {})
    channels = mapping.get("channels", {})
    tone = style.get("tone", {})
    stretch = tone.get("stretch", {})
    gain = tone.get("gain", {})
    percentiles = tone.get("percentiles", {})

    for plane_name in plane_names:
        st.session_state[_enabled_key(plane_name)] = plane_name in enabled if enabled else True

    for channel in ("red", "green", "blue"):
        weights = {
            str(item["plane"]): float(item["weight"])
            for item in channels.get(channel, [])
            if isinstance(item, dict) and "plane" in item
        }
        for plane_name in plane_names:
            st.session_state[_weight_key(channel, plane_name)] = weights.get(plane_name, 0.0)

        st.session_state[f"tone:gain:{channel}"] = float(gain.get(channel, 1.0))
        stretch_cfg = stretch.get(channel, {})
        st.session_state[f"tone:stretch-kind:{channel}"] = str(stretch_cfg.get("kind", "asinh"))
        st.session_state[f"tone:stretch-parameter:{channel}"] = float(stretch_cfg.get("parameter", 4.0))

    st.session_state["tone:black"] = float(percentiles.get("black", 1.0))
    st.session_state["tone:white"] = float(percentiles.get("white", 99.5))
    st.session_state["tone:saturation"] = float(tone.get("saturation", 1.0))


def _enabled_key(plane_name: str) -> str:
    return f"plane:enabled:{plane_name}"


def _weight_key(channel: str, plane_name: str) -> str:
    return f"mapping:{channel}:{plane_name}"


def _ensure_default(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


if __name__ == "__main__":  # pragma: no cover
    main()

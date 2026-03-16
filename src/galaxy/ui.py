from __future__ import annotations

import json
from pathlib import Path
import sys

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
    enabled = {name for name in planes if st.sidebar.checkbox(name, value=True)}

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
            weight = st.sidebar.slider(f"{channel}:{plane_name}", min_value=0.0, max_value=3.0, value=1.0 if plane_name in _default_channel_members(channel, plane_names) else 0.0, step=0.05)
            if weight > 0:
                channels[channel].append(ChannelContribution(plane=plane_name, weight=weight))
    return MappingConfig(defaults=MappingDefaults(strategy="wavelength_order"), channels=channels, derived_planes=[])


def _tone_controls() -> ToneConfig:
    st.sidebar.header("Tone")
    black = st.sidebar.slider("Black percentile", 0.0, 20.0, 1.0, 0.1)
    white = st.sidebar.slider("White percentile", 80.0, 100.0, 99.5, 0.1)
    saturation = st.sidebar.slider("Saturation", 0.0, 3.0, 1.0, 0.05)
    gains = {}
    stretch = {}
    for channel in ("red", "green", "blue"):
        gains[channel] = st.sidebar.slider(f"{channel.title()} gain", 0.0, 3.0, 1.0, 0.05)
        kind = st.sidebar.selectbox(f"{channel.title()} stretch", ("asinh", "gamma"), index=0, key=f"stretch-{channel}")
        parameter = st.sidebar.slider(f"{channel.title()} stretch parameter", 0.1, 10.0, 4.0, 0.1, key=f"stretch-p-{channel}")
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


if __name__ == "__main__":  # pragma: no cover
    main()

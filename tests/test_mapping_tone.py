import numpy as np

from galaxy.config import MappingConfig, ToneConfig
from galaxy.mapping import CompositionInputs, compose_channels
from galaxy.tone import apply_tone


def test_mapping_and_tone_generate_rgb_cube() -> None:
    planes = {
        "blue_plane": np.full((8, 8), 1.0, dtype=np.float32),
        "green_plane": np.full((8, 8), 2.0, dtype=np.float32),
        "red_plane": np.full((8, 8), 3.0, dtype=np.float32),
    }
    metadata = {
        "blue_plane": {"filter": "F090W"},
        "green_plane": {"filter": "F200W"},
        "red_plane": {"filter": "F444W"},
    }
    mapping = MappingConfig.model_validate(
        {
            "planes": [
                {"plane": "red_plane", "rgb": {"red": 1.0, "green": 0.0, "blue": 0.0}},
                {"plane": "green_plane", "rgb": {"red": 0.0, "green": 1.0, "blue": 0.0}},
                {"plane": "blue_plane", "rgb": {"red": 0.0, "green": 0.0, "blue": 1.0}},
            ]
        }
    )
    tone = ToneConfig.model_validate(
        {
            "stretch": {
                "red": {"kind": "asinh", "parameter": 4.0},
                "green": {"kind": "asinh", "parameter": 4.0},
                "blue": {"kind": "asinh", "parameter": 4.0},
            },
            "percentiles": {"black": 0.0, "white": 100.0},
        }
    )
    composed = compose_channels(CompositionInputs(planes=planes, metadata=metadata), mapping)
    rgb = apply_tone(composed, tone)
    assert rgb.shape == (8, 8, 3)
    assert rgb.dtype == np.float32 or rgb.dtype == np.float64


def test_filter_based_plane_mapping_matches_metadata_filters() -> None:
    planes = {
        "jwst_f444w": np.full((4, 4), 5.0, dtype=np.float32),
        "jwst_f300m": np.full((4, 4), 3.0, dtype=np.float32),
        "jwst_f140m": np.full((4, 4), 1.0, dtype=np.float32),
    }
    metadata = {
        "jwst_f444w": {"filter": "F444W"},
        "jwst_f300m": {"filter": "F300M"},
        "jwst_f140m": {"filter": "F140M"},
    }
    mapping = MappingConfig.model_validate(
        {
            "planes": [
                {"filter": "F444W", "label": "dust", "rgb": {"red": 1.0, "green": 0.2, "blue": 0.0}},
                {"filter": "F300M", "label": "gas", "rgb": {"red": 0.0, "green": 1.0, "blue": 0.2}},
                {"filter": "F140M", "label": "stars", "rgb": {"red": 0.1, "green": 0.2, "blue": 1.0}},
            ]
        }
    )

    composed = compose_channels(CompositionInputs(planes=planes, metadata=metadata), mapping)

    assert np.allclose(composed["red"], 5.1)
    assert np.allclose(composed["green"], 4.2)
    assert np.allclose(composed["blue"], 1.6)


def test_default_mapping_spreads_planes_across_continuum() -> None:
    planes = {
        "f090w": np.ones((2, 2), dtype=np.float32),
        "f200w": np.ones((2, 2), dtype=np.float32),
        "f444w": np.ones((2, 2), dtype=np.float32),
    }
    metadata = {
        "f090w": {"filter": "F090W"},
        "f200w": {"filter": "F200W"},
        "f444w": {"filter": "F444W"},
    }
    mapping = MappingConfig.model_validate({})

    composed = compose_channels(CompositionInputs(planes=planes, metadata=metadata), mapping)

    assert composed["blue"][0, 0] > 0.0
    assert composed["green"][0, 0] > 0.0
    assert composed["red"][0, 0] > 0.0
    assert composed["green"][0, 0] >= composed["blue"][0, 0]

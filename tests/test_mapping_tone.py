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
    metadata = {name: {"filter": name} for name in planes}
    mapping = MappingConfig.model_validate(
        {
            "channels": {
                "red": [{"plane": "red_plane", "weight": 1.0}],
                "green": [{"plane": "green_plane", "weight": 1.0}],
                "blue": [{"plane": "blue_plane", "weight": 1.0}],
            }
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

import pytest

from galaxy.config import GalaxyConfig


def test_config_validation_accepts_valid_document() -> None:
    config = GalaxyConfig.model_validate(
        {
            "target": {"name": "Orion Nebula", "region": {"kind": "circle", "radius_arcmin": 5.0}},
            "canvas": {
                "center": {"mode": "resolved_target"},
                "pixel_scale_arcsec": 0.1,
                "width": 512,
                "height": 512,
            },
            "tone": {
                "stretch": {
                    "red": {"kind": "asinh", "parameter": 4.0},
                    "green": {"kind": "asinh", "parameter": 4.0},
                    "blue": {"kind": "asinh", "parameter": 4.0},
                },
                "percentiles": {"black": 1.0, "white": 99.0},
            },
        }
    )
    assert config.target.name == "Orion Nebula"


def test_config_validation_rejects_bad_percentiles() -> None:
    with pytest.raises(Exception):
        GalaxyConfig.model_validate(
            {
                "target": {"name": "Orion Nebula", "region": {"kind": "circle", "radius_arcmin": 5.0}},
                "canvas": {
                    "center": {"mode": "resolved_target"},
                    "pixel_scale_arcsec": 0.1,
                    "width": 512,
                    "height": 512,
                },
                "tone": {
                    "stretch": {
                        "red": {"kind": "asinh", "parameter": 4.0},
                        "green": {"kind": "asinh", "parameter": 4.0},
                        "blue": {"kind": "asinh", "parameter": 4.0},
                    },
                    "percentiles": {"black": 99.0, "white": 1.0},
                },
            }
        )

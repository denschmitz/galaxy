import pytest

from galaxy.config import GalaxyConfig, TargetConfig
from galaxy.targeting import resolve_target


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


def test_target_resolution_prefers_explicit_coordinates_over_name() -> None:
    target = TargetConfig.model_validate(
        {
            "name": "Pillars of Creation",
            "ra_deg": 274.7003,
            "dec_deg": -13.8067,
            "region": {"kind": "circle", "radius_arcmin": 1.0},
        }
    )
    resolved = resolve_target(target)
    assert resolved.source == "explicit-decimal"
    assert resolved.coord.ra.deg == pytest.approx(274.7003)
    assert resolved.coord.dec.deg == pytest.approx(-13.8067)


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

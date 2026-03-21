import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord

from galaxy.config import GalaxyConfig, TargetConfig
from galaxy.targeting import region_to_mast_shape, resolve_target


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


def test_target_resolution_prefers_sexagesimal_over_name() -> None:
    target = TargetConfig.model_validate(
        {
            "name": "Ignored Name",
            "ra": "05:35:17.3",
            "dec": "-05:23:28",
            "region": {"kind": "circle", "radius_arcmin": 1.0},
        }
    )
    resolved = resolve_target(target)
    expected = SkyCoord("05:35:17.3", "-05:23:28", unit=(u.hourangle, u.deg), frame="icrs")

    assert resolved.source == "explicit-sexagesimal"
    assert resolved.coord.ra.deg == pytest.approx(expected.ra.deg)
    assert resolved.coord.dec.deg == pytest.approx(expected.dec.deg)


def test_box_region_is_translated_to_circumscribed_circle_for_mast() -> None:
    target = TargetConfig.model_validate(
        {
            "ra_deg": 10.0,
            "dec_deg": 20.0,
            "region": {"kind": "box", "width_arcmin": 2.0, "height_arcmin": 1.0},
        }
    )
    resolved = resolve_target(target)
    shape_kind, shape_kwargs = region_to_mast_shape(target.region, resolved.coord)

    assert shape_kind == "circle"
    assert shape_kwargs["source_region"] == "box-approximated-as-circle"
    assert shape_kwargs["width"] == pytest.approx(2.0 / 60.0)
    assert shape_kwargs["height"] == pytest.approx(1.0 / 60.0)


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

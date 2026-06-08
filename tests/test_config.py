import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord

from galaxy.config import (
    PROJECT_FORMAT_REVISION,
    GalaxyConfig,
    TargetConfig,
    dump_config,
    load_config,
    validate_config_dict,
    validate_config_document,
)
from galaxy.targeting import region_to_mast_shape, resolve_target


def _minimal_search_project() -> dict:
    return {
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


def test_config_validation_accepts_valid_document() -> None:
    config = GalaxyConfig.model_validate(_minimal_search_project())
    assert config.target is not None
    assert config.target.name == "Orion Nebula"
    assert config.format_revision == PROJECT_FORMAT_REVISION


def test_pinned_project_validation_accepts_explicit_source_products_without_target() -> None:
    config = GalaxyConfig.model_validate(
        {
            "search": {
                "source_products": [
                    {
                        "stable_product_identifier": "jwst_nircam_f200w_i2d.fits",
                        "mission": "JWST",
                        "filter": "F200W",
                    }
                ]
            },
            "canvas": {
                "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
                "pixel_scale_arcsec": 0.1,
                "width": 512,
                "height": 512,
            },
            "mapping": {"planes": [{"filter": "F200W", "rgb": {"red": 1.0, "green": 1.0, "blue": 1.0}}]},
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

    assert config.target is None
    assert config.search.source_products[0].stable_product_identifier == "jwst_nircam_f200w_i2d.fits"


def test_validate_config_reports_unknown_fields_with_field_specific_diagnostics() -> None:
    _, errors = validate_config_dict(
        {
            **_minimal_search_project(),
            "canvas": {
                "center": {"mode": "resolved_target"},
                "pixel_scale_arcsec": 0.1,
                "width": 512,
                "height": 512,
                "bogus": True,
            },
            "unexpected": 1,
        }
    )

    assert any("canvas.bogus: [unknown_field]" in error for error in errors)
    assert any("unexpected: [unknown_field]" in error for error in errors)


def test_validate_config_reports_unsupported_revision() -> None:
    _, issues = validate_config_document({**_minimal_search_project(), "format_revision": PROJECT_FORMAT_REVISION + 1})

    assert any(issue.code == "unsupported_format_revision" for issue in issues)
    assert any(issue.path == "<root>" for issue in issues)


def test_config_round_trip_preserves_defined_fields(tmp_path) -> None:
    source = GalaxyConfig.model_validate(
        {
            **_minimal_search_project(),
            "search": {
                "filters": ["F090W", "F200W"],
                "source_products": [
                    {
                        "stable_product_identifier": "example.fits",
                        "product_type": "SCIENCE",
                    }
                ],
            },
            "canvas": {
                "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
                "pixel_scale_arcsec": 0.1,
                "width": 512,
                "height": 512,
                "view_state": {"zoom": 1.5, "pan_x": 12.0, "pan_y": -4.0},
            },
            "planes": {"enabled_filters": ["F090W"], "disabled_plane_ids": ["plane-b"]},
            "mapping": {"planes": [{"filter": "F090W", "label": "blue", "rgb": {"blue": 1.0}}]},
            "psf": {"enabled": True},
        }
    )
    path = tmp_path / "project.yaml"

    dump_config(source, path)
    loaded = load_config(path)

    assert loaded.model_dump(mode="json", exclude_none=True) == source.model_dump(mode="json", exclude_none=True)


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

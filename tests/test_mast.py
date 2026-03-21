from pathlib import Path
import uuid

import numpy as np

from galaxy.config import SearchConfig
from galaxy.mast import (
    apply_selection_policy,
    build_candidate_manifest,
    build_candidates,
    discover_candidates,
    filter_products,
    rank_product,
    select_products,
)
from galaxy.selection import SelectionInputs, load_candidate_manifest, write_candidate_manifest


def _make_temp_dir() -> Path:
    root = Path.cwd() / ".tmp_test_mast"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    return path


def _sample_products() -> list[dict[str, object]]:
    return [
        {
            "obsid": "1",
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "jwst_a_i2d.fits",
            "productSubGroupDescription": "I2D",
            "_obs_t_max": 1.0,
            "_obs_exptime": 100.0,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM",
            "dataURI": "mast:jwst_a_i2d",
        },
        {
            "obsid": "1",
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "jwst_a_cal.fits",
            "productSubGroupDescription": "CAL",
            "_obs_t_max": 1.0,
            "_obs_exptime": 100.0,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM",
            "dataURI": "mast:jwst_a_cal",
        },
        {
            "obsid": "2",
            "obs_id": "B",
            "filters": "F673N",
            "productType": "SCIENCE",
            "productFilename": "hst_b_drc.fits",
            "productSubGroupDescription": "DRC",
            "_obs_t_max": 5.0,
            "_obs_exptime": 300.0,
            "_obs_collection": "HST",
            "_obs_instrument": "WFC3/UVIS",
            "dataURI": "mast:hst_b_drc",
        },
        {
            "obsid": "3",
            "obs_id": "C",
            "filters": "F090W",
            "productType": "SCIENCE",
            "productFilename": "jwst_c_i2d.fits",
            "productSubGroupDescription": "I2D",
            "_obs_t_max": 3.0,
            "_obs_exptime": 200.0,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM",
            "dataURI": "mast:jwst_c_i2d",
        },
    ]


def test_filter_products_respects_filters_and_type() -> None:
    rows = [
        {"detector": "WFC3", "filters": "F606W", "productType": "SCIENCE", "productFilename": "a_drc.fits", "productSubGroupDescription": "DRC", "_obs_collection": "HST"},
        {"detector": "NIRCAM", "filters": "F200W", "productType": "SCIENCE", "productFilename": "b_i2d.fits", "productSubGroupDescription": "I2D", "_obs_collection": "JWST"},
    ]
    filtered = filter_products(
        rows,
        SearchConfig(detectors=["NIRCAM"], filters=["F200W"], product_types=["SCIENCE"]),
    )
    assert filtered == [rows[1]]


def test_filter_products_drops_non_display_products() -> None:
    rows = [
        {"filters": "BLANK", "productType": "SCIENCE", "productFilename": "n6298aweq_cal.fits", "productSubGroupDescription": "CAL", "_obs_collection": "HST"},
        {"filters": "F200W", "productType": "SCIENCE", "productFilename": "jw02739_f200w_cal.fits", "productSubGroupDescription": "CAL", "_obs_collection": "JWST"},
        {"filters": "F200W", "productType": "SCIENCE", "productFilename": "jw02739_f200w_i2d.fits", "productSubGroupDescription": "I2D", "_obs_collection": "JWST"},
        {"filters": "F673N", "productType": "SCIENCE", "productFilename": "ick909050_drc.fits", "productSubGroupDescription": "DRC", "_obs_collection": "HST"},
    ]
    filtered = filter_products(rows, SearchConfig(product_types=["SCIENCE"]))
    assert filtered == [rows[2], rows[3]]


def test_select_products_is_deterministic_and_prefers_newer_version() -> None:
    products = [
        {
            "obsid": "1",
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "a_v1_i2d.fits",
            "productSubGroupDescription": "I2D v1",
            "_obs_t_max": 1.0,
            "_obs_exptime": 100.0,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM",
            "dataURI": "mast:a_v1_i2d",
        },
        {
            "obsid": "1",
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "a_v3_i2d.fits",
            "productSubGroupDescription": "I2D v3",
            "_obs_t_max": 1.0,
            "_obs_exptime": 100.0,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM",
            "dataURI": "mast:a_v3_i2d",
        },
    ]
    selected = select_products(products)
    assert selected[0]["productFilename"] == "a_v3_i2d.fits"
    assert rank_product(selected[0]) < rank_product(products[0])


def test_apply_selection_policy_can_keep_latest_per_filter() -> None:
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    selected = [
        item.product_filename
        for item in apply_selection_policy(
            candidates,
            SearchConfig(observation_selection="latest_per_filter", max_observations_per_filter=1),
        )
        if item.selected
    ]
    assert selected == ["jwst_c_i2d.fits", "jwst_a_i2d.fits", "hst_b_drc.fits"]


def test_apply_selection_policy_can_keep_more_than_one_per_filter() -> None:
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    selected = [
        item.product_filename
        for item in apply_selection_policy(
            candidates,
            SearchConfig(observation_selection="latest_per_filter", max_observations_per_filter=2),
        )
        if item.selected
    ]
    assert sorted(selected) == ["hst_b_drc.fits", "jwst_a_i2d.fits", "jwst_c_i2d.fits"]


def test_apply_selection_policy_can_keep_deepest_per_filter() -> None:
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    selected = [
        item.product_filename
        for item in apply_selection_policy(
            candidates,
            SearchConfig(observation_selection="deepest_per_filter", max_observations_per_filter=1),
        )
        if item.selected
    ]
    assert selected == ["jwst_c_i2d.fits", "jwst_a_i2d.fits", "hst_b_drc.fits"]


def test_apply_selection_policy_all_selects_best_candidate_per_observation_filter() -> None:
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    selected = [
        item.product_filename
        for item in apply_selection_policy(
            candidates,
            SearchConfig(observation_selection="all", max_observations_per_filter=1),
        )
        if item.selected
    ]
    assert selected == ["jwst_c_i2d.fits", "jwst_a_i2d.fits", "hst_b_drc.fits"]


def test_explicit_include_and_exclude_override_auto_policy() -> None:
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    selection_inputs = SelectionInputs(include_obsids={"A"}, exclude_obsids={"B"}, strategy="latest_per_filter")
    selected = apply_selection_policy(candidates, SearchConfig(observation_selection="latest_per_filter"), selection_inputs)
    selected_names = [item.product_filename for item in selected if item.selected]
    assert "jwst_a_i2d.fits" in selected_names
    assert "hst_b_drc.fits" not in selected_names


def test_candidate_manifest_round_trip() -> None:
    temp_dir = _make_temp_dir()
    candidates = build_candidates([item for item in _sample_products() if item["productFilename"] != "jwst_a_cal.fits"])
    manifest = build_candidate_manifest(
        candidates,
        SearchConfig(observation_selection="latest_per_filter", max_observations_per_filter=1),
        config_path="example.yaml",
        selection_inputs=SelectionInputs(max_total=2),
    )
    path = temp_dir / "candidates.json"
    write_candidate_manifest(manifest, path)
    loaded = load_candidate_manifest(path)
    assert loaded.config_path == "example.yaml"
    assert loaded.selection_inputs.max_total == 2
    assert len(loaded.candidates) == len(manifest.candidates)


def test_candidate_manifest_serializes_masked_values_as_null() -> None:
    temp_dir = _make_temp_dir()
    candidates = build_candidates(
        [
            {
                "obsid": "1",
                "obs_id": "A",
                "filters": "F200W",
                "productType": "SCIENCE",
                "productFilename": "masked_i2d.fits",
                "productSubGroupDescription": "I2D",
                "_obs_collection": "JWST",
                "dataURI": "mast:masked",
                "proposal_id": np.ma.masked,
                "target_name": np.ma.masked,
            }
        ]
    )
    path = temp_dir / "candidates.json"
    write_candidate_manifest(build_candidate_manifest(candidates, SearchConfig()), path)
    payload = path.read_text(encoding="utf-8")

    assert '"proposal_id": null' in payload
    assert '"target_name": null' in payload


def test_discover_candidates_rejects_polygon_queries() -> None:
    try:
        discover_candidates("polygon", {"coordinates": []}, SearchConfig())
    except ValueError as exc:
        assert "circle queries only" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected discover_candidates to reject polygon queries")

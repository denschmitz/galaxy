from pathlib import Path
import uuid

import numpy as np
import pytest

from galaxy.processing_config import SearchConfig
from galaxy.mast import (
    ArchiveQueryStatus,
    SearchResult,
    apply_selection_policy,
    build_candidate_manifest,
    build_candidates,
    discover_candidates,
    download_selected,
    _enrich_products,
    filter_products,
    rank_product,
    query_archive_outcome,
    select_products,
)
from galaxy.selection import SelectionInputs, load_candidate_manifest, write_candidate_manifest


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (SearchResult([], []), ArchiveQueryStatus.EMPTY),
        (SearchResult([], [], complete=False, message="page 2 unavailable"), ArchiveQueryStatus.INCOMPLETE),
    ],
)
def test_archive_query_outcome_distinguishes_empty_and_incomplete(result, status) -> None:
    outcome = query_archive_outcome(
        "circle", {"ra": 1.0, "dec": 2.0, "radius": 0.1}, SearchConfig(),
        query=lambda *args, **kwargs: result,
    )
    assert outcome.status is status


def test_archive_query_outcome_distinguishes_failure() -> None:
    outcome = query_archive_outcome(
        "circle", {"ra": 1.0, "dec": 2.0, "radius": 0.1}, SearchConfig(),
        query=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("MAST offline")),
    )
    assert outcome.status is ArchiveQueryStatus.FAILED
    assert outcome.message == "MAST offline"


def test_unavailable_download_reports_exact_selected_product(tmp_path, monkeypatch) -> None:
    candidate = build_candidates([_sample_products()[0]])[0]
    candidate.selected = True
    monkeypatch.setattr(
        "galaxy.mast.Observations.download_file",
        lambda *args, **kwargs: ("ERROR", "not found", "mast:missing"),
    )
    downloaded, skipped = download_selected([candidate], tmp_path)
    assert downloaded == []
    assert skipped[0]["candidate_id"] == candidate.candidate_id
    assert skipped[0]["stable_product_identifier"] == "jwst_a_i2d.fits"
    assert skipped[0]["reason"] == "not found"


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


def test_product_enrichment_uses_parent_observation_metadata() -> None:
    products = [{"obsID": "component-1", "parent_obsid": "parent-1", "productFilename": "component_i2d.fits"}]
    metadata = {
        "parent-1": {
            "_obs_exptime": 123.0,
            "_obs_instrument": "NIRCAM/IMAGE",
            "_obs_s_region": "POLYGON ICRS 1 2 3 4 5 6",
        }
    }

    enriched = _enrich_products(products, metadata)

    assert enriched[0]["_obs_exptime"] == 123.0
    assert enriched[0]["_obs_instrument"] == "NIRCAM/IMAGE"
    assert enriched[0]["_obs_s_region"].startswith("POLYGON")


def test_selection_prefers_level3_association_mosaic_within_parent_observation() -> None:
    products = [
        {
            "obsID": "association",
            "parent_obsid": "89223710",
            "filters": "F090W",
            "productType": "SCIENCE",
            "productFilename": "jw02739-o001_t001_nircam_clear-f090w_i2d.fits",
            "productSubGroupDescription": "I2D",
            "calib_level": 3,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM/IMAGE",
            "dataURI": "mast:JWST/product/jw02739-o001_t001_nircam_clear-f090w_i2d.fits",
        },
        {
            "obsID": "detector-a4",
            "parent_obsid": "89223710",
            "filters": "F090W",
            "productType": "SCIENCE",
            "productFilename": "jw02739001004_04101_00005_nrca4_i2d.fits",
            "productSubGroupDescription": "I2D",
            "calib_level": 2,
            "_obs_collection": "JWST",
            "_obs_instrument": "NIRCAM/IMAGE",
            "dataURI": "mast:JWST/product/jw02739001004_04101_00005_nrca4_i2d.fits",
        },
    ]

    selected = apply_selection_policy(
        build_candidates(products),
        SearchConfig(observation_selection="deepest_per_filter", max_observations_per_filter=1),
    )

    by_name = {candidate.product_filename: candidate for candidate in selected}
    assert by_name["jw02739-o001_t001_nircam_clear-f090w_i2d.fits"].selected
    assert not by_name["jw02739001004_04101_00005_nrca4_i2d.fits"].selected
    assert by_name["jw02739001004_04101_00005_nrca4_i2d.fits"].selected_reason == (
        "dropped:lower_ranked_product_in_observation_filter"
    )


def test_deepest_selection_ranks_known_exposure_ahead_of_unknown_depth() -> None:
    products = [
        {
            "obsID": "known",
            "parent_obsid": "known-parent",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "known_i2d.fits",
            "productSubGroupDescription": "I2D",
            "calib_level": 3,
            "_obs_exptime": 100.0,
            "_obs_collection": "JWST",
            "dataURI": "mast:known",
        },
        {
            "obsID": "unknown",
            "parent_obsid": "unknown-parent",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "unknown_i2d.fits",
            "productSubGroupDescription": "I2D",
            "calib_level": 3,
            "_obs_collection": "JWST",
            "dataURI": "mast:unknown",
        },
    ]

    selected = apply_selection_policy(
        build_candidates(products),
        SearchConfig(observation_selection="deepest_per_filter", max_observations_per_filter=1),
    )

    by_name = {candidate.product_filename: candidate for candidate in selected}
    assert by_name["known_i2d.fits"].selected
    assert by_name["unknown_i2d.fits"].selected_reason == "dropped:unknown_depth_not_selected"


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

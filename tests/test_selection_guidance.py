from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from galaxy.mast import build_candidate_manifest, build_candidates
from galaxy.processing_config import SearchConfig
from galaxy.scene_card import document, load_scene, save_scene
from galaxy.scene_models import SceneCard
from galaxy.scene_workflow import (
    default_scene_path, draft_from_target, manifest_from_scene_asset,
    persist_candidate_manifest,
)
from galaxy.selection import CandidateManifest, CandidateRecord, write_candidate_manifest
from galaxy.selection_guidance import (
    apply_selection_mode, grouped_candidates, recommendation_explanation,
    selection_summary, set_custom_selection,
)


NOW = "2026-09-22T02:00:00Z"


def _product(
    identity: str, *, mission: str = "JWST", instrument: str = "NIRCAM/IMAGE",
    filter_name: str = "F200W", exposure: float | None = 100.0,
    size: int | None = 1024,
) -> dict[str, object]:
    return {
        "obsid": f"parent-{identity}", "obsID": f"obs-{identity}",
        "filters": filter_name, "productType": "SCIENCE",
        "productFilename": f"{identity}_i2d.fits", "productSubGroupDescription": "I2D",
        "calib_level": 3, "_obs_exptime": exposure, "_obs_collection": mission,
        "_obs_instrument": instrument, "dataURI": f"mast:{identity}", "size": size,
    }


def _manifest(products: list[dict[str, object]]) -> CandidateManifest:
    return build_candidate_manifest(
        build_candidates(products),
        SearchConfig(observation_selection="deepest_per_filter", max_observations_per_filter=1),
    )


def test_duplicate_download_identity_is_consolidated_and_conflicts_are_explicit() -> None:
    first = _product("same", exposure=100.0, size=1024)
    second = dict(first, _obs_exptime=250.0, size=2048, obsID="another-row")

    candidates = build_candidates([first, second])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.exposure_time is None
    assert candidate.file_size is None
    assert candidate.obs_id is None
    assert candidate.extra_metadata["source_row_count"] == 2
    assert candidate.extra_metadata["metadata_conflicts"]["exposure_time"] == [100.0, 250.0]


def test_manifest_consolidation_is_idempotent_and_preserves_conflict_sources() -> None:
    first = _product("same", exposure=10.0)
    second = dict(first, _obs_exptime=20.0)
    candidates = build_candidates([first, second])
    manifest = build_candidate_manifest(candidates, SearchConfig())
    assert manifest.candidates[0].extra_metadata["source_row_count"] == 2
    assert len(manifest.candidates[0].extra_metadata["source_records"]) == 2


def test_guided_modes_remain_bounded_after_explicit_includes() -> None:
    products = [
        _product("a1", filter_name="F090W"),
        _product("a2", filter_name="F090W", exposure=50.0),
        _product("b", filter_name="F200W"),
        _product("c", filter_name="F356W"),
        _product("d", filter_name="F444W"),
    ]
    manifest = _manifest(products)
    manifest.selection_inputs.include_products = {
        item.candidate_id for item in manifest.candidates
    }
    full = apply_selection_mode(manifest, "one_per_filter", "all")
    assert selection_summary(full).selected_products == 4
    assert all(group.selected_count <= 1 for group in grouped_candidates(full))
    preview = apply_selection_mode(manifest, "preview_set", "all")
    assert selection_summary(preview).selected_products == 3
    assert all(group.selected_count <= 1 for group in grouped_candidates(preview))


def test_modes_scopes_groups_and_summary_use_unique_products() -> None:
    products = [
        _product("j1", filter_name="F090W", size=1024),
        _product("j2", filter_name="F200W", size=2048),
        _product("j3", filter_name="F444W", size=None),
        _product("j4", instrument="MIRI/IMAGE", filter_name="F770W", size=4096),
        _product("h1", mission="HST", instrument="WFC3/IR", filter_name="F160W", size=512),
    ]
    manifest = _manifest(products)
    all_policy = build_candidate_manifest(
        build_candidates(products), SearchConfig(observation_selection="all"),
    )
    assert all_policy.selection_mode == "custom"
    assert CandidateManifest.from_dict(all_policy.to_dict()).selection_mode == "custom"

    full = apply_selection_mode(manifest, "one_per_filter", "all")
    assert selection_summary(full).selected_products == 5
    assert len(grouped_candidates(full)) == 5

    preview = apply_selection_mode(manifest, "preview_set", "all")
    assert selection_summary(preview).selected_products == 3
    assert [item.candidate_id for item in preview.candidates if item.selected] == [
        item.candidate_id for item in apply_selection_mode(manifest, "preview_set", "all").candidates
        if item.selected
    ]

    hst = apply_selection_mode(manifest, "one_per_filter", "hst")
    assert {item.mission for item in hst.candidates if item.selected} == {"HST"}
    jwst = apply_selection_mode(manifest, "one_per_filter", "jwst")
    assert {item.mission for item in jwst.candidates if item.selected} == {"JWST"}
    assert selection_summary(jwst).unknown_size_products == 1
    summary = selection_summary(hst)
    assert summary.available_products == 5
    assert summary.selected_products == 1
    assert summary.known_download_bytes == 512
    assert summary.unknown_size_products == 0


def test_custom_selection_does_not_add_automatic_products() -> None:
    full = apply_selection_mode(
        _manifest([_product("one"), _product("one-alt"), _product("two", filter_name="F444W")]),
        "one_per_filter", "all",
    )
    chosen = {full.candidates[0].candidate_id}
    custom = set_custom_selection(full, chosen)
    recalculated = apply_selection_mode(custom, "custom", "all")
    assert {item.candidate_id for item in recalculated.candidates if item.selected} == chosen


def test_custom_selection_retains_the_mode_used_for_restore() -> None:
    preview = apply_selection_mode(
        _manifest([_product("one"), _product("one-alt"), _product("two", filter_name="F444W")]),
        "preview_set", "all",
    )
    custom = apply_selection_mode(preview, "custom", "all")
    assert custom.selection_mode == "custom"
    assert custom.recommendation_mode == "preview_set"


def test_explanation_is_concise_and_never_exposes_internal_reason_codes() -> None:
    candidate = _manifest([_product("one", exposure=None, size=None)]).candidates[0]
    candidate.extra_metadata["metadata_conflicts"] = {"exposure_time": [10.0, 20.0]}

    explanation = recommendation_explanation(candidate)

    assert len(explanation.split(" · ")) <= 5
    assert "selected:" not in explanation
    assert "dropped:" not in explanation
    assert "conflict" in explanation


def test_scene_owned_manifest_saves_and_restores_before_apply(tmp_path: Path) -> None:
    card = draft_from_target(
        name="Horsehead", ra_deg=85.25, dec_deg=-2.4,
        width_arcmin=2.0, height_arcmin=2.0,
    )
    scene_path = default_scene_path(card, tmp_path)
    manifest = apply_selection_mode(_manifest([_product("one")]), "preview_set", "all")

    associated, asset_path = persist_candidate_manifest(card, scene_path, manifest)
    committed = save_scene(associated, scene_path)
    reopened = load_scene(scene_path)
    restored = manifest_from_scene_asset(reopened, scene_path)

    assert asset_path.is_file()
    assert committed.discovery.candidate_manifest_asset_id
    assert restored is not None
    assert restored.to_dict() == manifest.to_dict()


def test_scene_manifest_reports_missing_and_corrupt_assets(tmp_path: Path) -> None:
    card = draft_from_target(
        name="Missing", ra_deg=1.0, dec_deg=2.0, width_arcmin=1.0, height_arcmin=1.0,
    )
    manifest = _manifest([_product("one")])
    missing_scene = default_scene_path(card, tmp_path / "missing")
    associated, manifest_path = persist_candidate_manifest(card, missing_scene, manifest)
    manifest_path.unlink()
    with pytest.raises(FileNotFoundError, match="missing"):
        manifest_from_scene_asset(associated, missing_scene)

    corrupt_scene = default_scene_path(card, tmp_path / "corrupt")
    associated, manifest_path = persist_candidate_manifest(card, corrupt_scene, manifest)
    manifest_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="wrong size|checksum"):
        manifest_from_scene_asset(associated, corrupt_scene)


def test_scene_rejects_unresolved_candidate_manifest_reference() -> None:
    card = draft_from_target(
        name="Broken", ra_deg=1.0, dec_deg=2.0, width_arcmin=1.0, height_arcmin=1.0,
    )
    data = document(card)
    data["discovery"] = {"candidate_manifest_asset_id": "missing", "archive_retrieved_at": NOW}
    with pytest.raises(ValidationError, match="candidate_manifest_asset_id"):
        SceneCard.model_validate(data)


def test_manifest_startup_shows_guided_controls_and_stage_guidance(tmp_path: Path) -> None:
    manifest_path = tmp_path / "candidates.json"
    write_candidate_manifest(_manifest([_product("one"), _product("one-alt"), _product("two", filter_name="F444W")]), manifest_path)
    scene_directory = tmp_path / "scenes"
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(scene_directory)!r}, {str(manifest_path)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )

    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)

    assert not app.exception
    assert "Selection mode" in [item.label for item in app.radio]
    assert "Mission scope" in [item.label for item in app.radio]
    assert "Clear selection" in [item.label for item in app.button]
    assert "Restore mode recommendation" in [item.label for item in app.button]
    assert "Technical readiness details" in [item.label for item in app.expander]
    assert any("3 unique products available" in item.value for item in app.caption)
    assert any(item.label.startswith("Show 1 alternatives") for item in app.expander)
    assert any("HST scope unavailable" in item.value for item in app.caption)
    assert any("Choose a selection mode and scope" in item.value for item in app.markdown)

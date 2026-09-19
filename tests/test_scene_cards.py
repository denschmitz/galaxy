from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from galaxy import scene_card as storage
from galaxy.scene_card import (
    append_render, asset_path, create_scene, dependency_issues, document, duplicate_scene,
    edit_scene, load_scene, save_scene,
)
from galaxy.scene_models import Asset, Inputs, SceneCard, effective_inputs
from galaxy.scene_readiness import readiness

NOW = "2026-09-11T12:00:00Z"


@pytest.fixture
def ready() -> SceneCard:
    card = create_scene("Fixture", now=NOW)
    return edit_scene(card, {
        "selection": {"products": [{"product_id": "mast:exact-v1", "filter": "F200W", "data_uri": "mast:exact-v1"}],
                      "selected_product_ids": ["mast:exact-v1"]},
        "canvas": {"center": {"mode": "explicit", "ra_deg": 12.0, "dec_deg": -10.0},
                   "projection": "TAN", "pixel_scale_arcsec": 0.1, "width": 100, "height": 80,
                   "rotation_deg": 0.0, "flux_conserving": True},
        "planes": {"enabled_filters": ["F200W"], "disabled_plane_ids": [], "export_multiplane_fits": False},
        "mapping": {"planes": [{"filter": "F200W", "rgb": {"red": 1.0, "green": 0.0, "blue": -0.1}}]},
        "tone": {"stretch": {c: {"kind": "asinh", "parameter": 4.0} for c in ("red", "green", "blue")},
                 "percentiles": {"black": 1.0, "white": 99.0},
                 "gain": {c: 1.0 for c in ("red", "green", "blue")},
                 "bias": {c: 0.0 for c in ("red", "green", "blue")}, "saturation": 1.0},
        "psf": {"enabled": False},
    })


def rendered(ready: SceneCard) -> SceneCard:
    return append_render(
        ready, snapshot=ready.model_copy(deep=True), branch="original",
        plane_filters={"plane-1": "F200W"}, image_asset_id="image", provenance_asset_id="prov",
        thumbnail_asset_id="thumb", now=NOW,
        assets={aid: Asset(kind=kind, path=f"assets/{aid}.bin")
                for aid, kind in (("image", "render_image"), ("prov", "provenance"), ("thumb", "render_thumbnail"))},
    )


def test_minimal_draft_round_trip_and_partial_fields(tmp_path: Path) -> None:
    card = create_scene(now=NOW)
    card = edit_scene(card, {"target": {"name": "Horsehead"},
                            "tone": {"stretch": {"red": {"kind": "asinh"}}}, "search": {"filters": []}})
    path = tmp_path / "scene.json"
    saved = save_scene(card, path, now=NOW)
    assert document(load_scene(path)) == document(saved) == document(card)
    assert "canvas" not in document(saved)
    assert document(saved)["search"]["filters"] == []
    assert readiness(saved, "name_resolution") == []
    assert readiness(saved, "render")
    assert readiness(saved, "discovery")


@pytest.mark.parametrize("changes", [
    {"schema_version": 2}, {"schema_version": True}, {"schema_version": 1.0},
    {"title": " "}, {"title": None}, {"scene_id": "NOT-A-UUID"},
    {"created_at": "2026-02-30T12:00:00Z"}, {"updated_at": "2026-09-10T12:00:00Z"},
    {"created_at": "2026-09-11T12:00:00+00:00"}, {"content_revision": 0},
    {"target": {"ra_deg": 360}}, {"target": {"dec_deg": -91}}, {"target": {"extra": 1}},
    {"canvas": {"width": True}}, {"canvas": {"width": "2"}}, {"canvas": {"pixel_scale_arcsec": 0}},
    {"canvas": {"rotation_deg": float("inf")}}, {"tone": {"saturation": float("nan")}},
    {"planes": {"enabled_filters": ["F", "F"]}},
    {"selection": {"products": [{"product_id": "x"}, {"product_id": "x"}]}},
    {"selection": {"selected_product_ids": ["x", "x"]}},
    {"mapping": {"planes": [{"filter": "F", "plane": "p"}]}},
    {"mapping": {"planes": [{"filter": "F"}, {"filter": "F"}]}},
    {"tone": {"percentiles": {"black": 90, "white": 10}}},
    {"psf": {"per_plane": {"p": {"max_iterations": 101}}}},
    {"search": {"observation_date_start": "2026-09-12T00:00:00Z", "observation_date_end": NOW}},
    {"bogus": 1},
])
def test_invalid_structure_rejected(changes: dict) -> None:
    with pytest.raises(ValidationError):
        SceneCard.model_validate({**document(create_scene(now=NOW)), **changes})


@pytest.mark.parametrize("path", ["../escape", "x/../../escape", "C:/escape", "C:escape", "/escape",
                                  "\\\\server\\share\\x", "safe:file", "."])
def test_unsafe_asset_paths_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        Asset(kind="source", path=path)


@pytest.mark.parametrize("entry", [
    {"kind": "source"}, {"kind": "source", "path": "a", "uri": "cache:b"},
    {"kind": "source", "uri": "not-a-uri"}, {"kind": "discovery_thumbnail", "path": "a"},
    {"kind": "source", "path": "a", "byte_count": -1}, {"kind": "source", "path": "a", "sha256": "bad"},
])
def test_invalid_assets(entry: dict) -> None:
    with pytest.raises(ValidationError):
        Asset.model_validate(entry)


def test_rotation_metadata_and_no_null(tmp_path: Path) -> None:
    card = edit_scene(create_scene(now=NOW), {
        "canvas": {"rotation_deg": 360}, "discovery": {"sources": [{
            "source_kind": "release_tracker", "source_url": "https://example.org/source",
            "retrieved_at": NOW, "extracted_metadata": {"unknown": None, "nested": [True, 1]},
        }]},
    })
    assert card.canvas.rotation_deg == 0
    assert save_scene(card, tmp_path / "card.json", now=NOW) == card
    with pytest.raises(ValidationError, match="null"):
        SceneCard.model_validate({**document(card), "canvas": {"center": None}})


def test_strict_json_load_and_unknown_version_preservation(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        path.write_text(text)
        with pytest.raises(ValueError):
            load_scene(path)
        assert path.read_text() == text
    data = document(create_scene(now=NOW))
    data["schema_version"] = 99
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        save_scene(create_scene(now=NOW), path, now=NOW)
    assert path.read_bytes() == before


def test_readiness_pins_mapping_and_branch(ready: SceneCard) -> None:
    context = {"plane-1": "F200W"}
    assert readiness(ready, "render", plane_filters=context) == []
    assert readiness(ready, "render")[0].code == "inspection_required"
    assert readiness(ready, "render", plane_filters=context, branch="deconvolved")
    assert readiness(edit_scene(ready, {"selection": {"products": [], "selected_product_ids": ["missing"]}}),
                     "render", plane_filters=context)
    assert readiness(edit_scene(ready, {"mapping": {"defaults": {"strategy": "continuum"}}}),
                     "render", plane_filters=context)
    assert readiness(edit_scene(ready, {"planes": {"enabled_filters": [], "disabled_plane_ids": [],
                                                   "export_multiplane_fits": False}}), "render", plane_filters=context)
    assert readiness(edit_scene(ready, {"mapping": {"planes": [{"filter": "F200W",
        "rgb": {"red": 0, "green": 0, "blue": 0}}]}}), "render", plane_filters=context)


def test_plane_override_and_derived_cycles(ready: SceneCard) -> None:
    mapping = document(ready)["mapping"]
    mapping["planes"].append({"plane": "plane-1", "rgb": {"red": 0, "green": 0, "blue": 0}})
    assert readiness(edit_scene(ready, {"mapping": mapping}), "render", plane_filters={"plane-1": "F200W"})
    mapping["derived_planes"] = [{"name": "loop", "operation": "linear_combination",
                                  "terms": [{"plane": "loop", "weight": 1}]}]
    issues = readiness(edit_scene(ready, {"mapping": mapping}), "render", plane_filters={"plane-1": "F200W"})
    assert any("cyclic" in p.message for p in issues)


def test_psf_readiness_does_not_break_original(ready: SceneCard) -> None:
    data = document(ready)
    data["psf"] = {"enabled": True, "per_plane": {"plane-1": {"enabled": True}}}
    card = SceneCard.model_validate(data)
    assert readiness(card, "render", plane_filters={"plane-1": "F200W"}) == []
    assert readiness(card, "render", plane_filters={"plane-1": "F200W"}, branch="deconvolved")
    data["assets"] = {"kernel": {"kind": "psf_kernel", "uri": "cache:kernel"}}
    data["psf"]["per_plane"]["plane-1"].update(kernel_asset_id="kernel", max_iterations=10, regularization=0)
    assert readiness(SceneCard.model_validate(data), "render", plane_filters={"plane-1": "F200W"},
                     branch="deconvolved") == []


def test_discovery_coordinates_and_search_policy() -> None:
    card = edit_scene(create_scene(now=NOW), {
        "target": {"ra_deg": 15, "dec_deg": 0, "coordinate_frame": "ICRS",
                   "region": {"kind": "circle", "radius_arcmin": 1}},
        "search": {"observation_selection": "all"},
    })
    assert readiness(card, "discovery") == []
    target = document(card)["target"]
    target.update(ra="02:00:00", dec="+00:00:00")
    assert any(p.code == "conflict" for p in readiness(edit_scene(card, {"target": target}), "discovery"))
    target["ra"] = "nonsense"
    assert any(p.code == "invalid" for p in readiness(edit_scene(card, {"target": target}), "discovery"))


def test_revisions_history_and_export_currency(ready: SceneCard, tmp_path: Path) -> None:
    card = rendered(ready)
    path = tmp_path / "scene.json"
    saved = save_scene(card, path, asset_contents={"image": b"image", "prov": b"{}", "thumb": b"thumb"}, now=NOW)
    edited = edit_scene(saved, {"title": "Renamed", "execution": {"fail_fast": True},
                               "canvas": {**document(saved)["canvas"], "view_state": {"zoom": 2}}})
    assert edited.content_revision == saved.content_revision
    assert edited.thumbnail_asset_id == "thumb"
    edited = edit_scene(edited, {"output": {"format": "png", "destination_directory": "exports"}})
    assert readiness(edited, "export") == []
    edited = edit_scene(edited, {"tone": {**document(edited)["tone"], "saturation": 2}})
    assert edited.content_revision == saved.content_revision + 1
    assert edited.thumbnail_asset_id is None
    assert edited.renders == saved.renders
    assert readiness(edited, "export")
    assert save_scene(edited, path, now=NOW).renders == saved.renders
    assert edit_scene(edited, {"tone": {**document(edited)["tone"], "saturation": 3}}).content_revision == edited.content_revision + 1


def test_render_snapshot_survives_inflight_edit(ready: SceneCard) -> None:
    changed = edit_scene(ready, {"canvas": {**document(ready)["canvas"], "width": 200}})
    historical = append_render(changed, snapshot=ready, branch="original", plane_filters={"p": "F200W"},
                               image_asset_id="i", provenance_asset_id="p", thumbnail_asset_id="t", now=NOW,
                               assets={aid: Asset(kind=kind, uri=f"cache:{aid}") for aid, kind in
                                       (("i", "render_image"), ("p", "provenance"), ("t", "render_thumbnail"))})
    assert historical.renders[0].inputs.canvas.width == 100
    assert historical.canvas.width == 200
    assert historical.thumbnail_asset_id is None
    ready.canvas.width = 300
    assert historical.renders[0].inputs.canvas.width == 100


def test_history_and_assets_cannot_be_rewritten(ready: SceneCard, tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    saved = save_scene(rendered(ready), path, asset_contents={"image": b"i", "prov": b"p", "thumb": b"t"}, now=NOW)
    original = path.read_bytes()
    data = document(saved)
    data["renders"][0]["created_at"] = "2026-09-11T11:00:00Z"
    with pytest.raises(ValueError, match="immutable"):
        save_scene(SceneCard.model_validate(data), path, now=NOW)
    with pytest.raises(ValueError, match="overwrite"):
        save_scene(saved, path, asset_contents={"image": b"different"}, now=NOW)
    data = document(saved)
    data["assets"]["image"]["path"] = "other.bin"
    with pytest.raises(ValueError, match="immutable"):
        save_scene(SceneCard.model_validate(data), path, now=NOW)
    assert path.read_bytes() == original


def test_invalid_history_and_references(ready: SceneCard) -> None:
    card = rendered(ready)
    for mutate in (
        lambda d: d["renders"][0]["inputs"]["tone"].clear(),
        lambda d: d["renders"][0].update(image_asset_id="unknown"),
        lambda d: d["renders"][0]["inputs"]["canvas"].update(width=200),
        lambda d: d.update(exports=[{"export_id": "e", "render_id": "unknown", "created_at": NOW,
                                    "format": "png", "destination": "x"}]),
    ):
        data = document(card)
        mutate(data)
        with pytest.raises(ValidationError):
            SceneCard.model_validate(data)
    with pytest.raises(ValidationError):
        Inputs.model_validate({"selection": {}, "canvas": {}, "planes": {}, "mapping": {}, "tone": {}, "psf": {}})


def test_atomic_replace_failure_preserves_old_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "scene.json"
    saved = save_scene(create_scene(now=NOW), path, now=NOW)
    original = path.read_bytes()
    def fail_replace(*args: object) -> None:
        raise OSError("injected replacement failure")
    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        save_scene(edit_scene(saved, {"title": "New"}), path, now=NOW)
    assert path.read_bytes() == original
    assert load_scene(path) == saved
    assert not list(tmp_path.glob("*.tmp"))


def test_binary_write_failure_does_not_publish_history(ready: SceneCard, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "scene.json"
    saved = save_scene(ready, path, now=NOW)
    original = path.read_bytes()
    def fail_sync(fd: int) -> None:
        raise OSError("injected fsync failure")
    monkeypatch.setattr(storage.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="injected"):
        save_scene(rendered(saved), path, asset_contents={"image": b"i", "prov": b"p", "thumb": b"t"}, now=NOW)
    assert path.read_bytes() == original


def test_missing_binary_and_checksum(tmp_path: Path) -> None:
    data = document(create_scene(now=NOW))
    data["assets"] = {"s": {"kind": "source", "path": "source.bin", "byte_count": 3,
                          "sha256": hashlib.sha256(b"abc").hexdigest()}}
    card = SceneCard.model_validate(data)
    path = tmp_path / "scene.json"
    with pytest.raises(ValueError, match="complete"):
        save_scene(card, path, now=NOW)
    assert not path.exists()
    with pytest.raises(ValueError, match="mismatch"):
        save_scene(card, path, asset_contents={"s": b"wrong"}, now=NOW)
    saved = save_scene(card, path, asset_contents={"s": b"abc"}, now=NOW)
    (tmp_path / "source.bin").unlink()
    assert dependency_issues(load_scene(path), path)[0].code == "missing"
    save_scene(edit_scene(saved, {"title": "Still usable draft"}), path, now=NOW)


def test_duplicate_independent_assets(ready: SceneCard, tmp_path: Path) -> None:
    data = document(rendered(ready))
    data["assets"]["source"] = {"kind": "source", "path": "data/source.fits"}
    source = tmp_path / "original.json"
    card = save_scene(SceneCard.model_validate(data), source,
                      asset_contents={"image": b"i", "prov": b"p", "thumb": b"t", "source": b"source"}, now=NOW)
    destination = tmp_path / "copy" / "copy.json"
    copied = duplicate_scene(card, source, destination, now=NOW)
    assert copied.scene_id != card.scene_id and copied.content_revision == 1
    assert copied.renders is None and copied.exports is None and copied.thumbnail_asset_id is None
    assert set(copied.assets) == {"source"}
    copy_asset = asset_path(destination, copied.assets["source"])
    copy_asset.write_bytes(b"changed")
    assert asset_path(source, card.assets["source"]).read_bytes() == b"source"
    with pytest.raises(ValueError, match="new file"):
        duplicate_scene(card, source, destination, now=NOW)


def test_symlink_escape_is_a_dependency_error(tmp_path: Path) -> None:
    root = tmp_path / "cards"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"OS does not permit test symlink creation: {exc}")
    asset = Asset(kind="source", path="link/source")
    with pytest.raises(ValueError, match="escapes"):
        asset_path(root / "scene.json", asset)


def test_generated_schema_matches_models(ready: SceneCard) -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "scene_card.schema.json"
    schema = json.loads(path.read_text())
    assert schema == SceneCard.model_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for card in (create_scene(now=NOW), ready, rendered(ready)):
        validator.validate(document(card))
    for fragment in ({"title": None}, {"canvas": {"width": "1"}}, {"unknown": True}):
        assert list(validator.iter_errors({**document(ready), **fragment}))

def test_exports_survive_edits_and_are_append_only(ready: SceneCard, tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    data = document(rendered(ready))
    data["exports"] = [{"export_id": "e1", "render_id": data["renders"][0]["render_id"],
                        "created_at": NOW, "format": "png", "destination": "outside/output.png"}]
    saved = save_scene(SceneCard.model_validate(data), path,
                       asset_contents={"image": b"i", "prov": b"p", "thumb": b"t"}, now=NOW)
    changed = edit_scene(saved, {"canvas": {**document(saved)["canvas"], "width": 200}})
    assert save_scene(changed, path, now=NOW).exports == saved.exports
    data = document(changed)
    data["exports"][0]["destination"] = "rewritten.png"
    with pytest.raises(ValueError, match="exports history"):
        save_scene(SceneCard.model_validate(data), path, now=NOW)


def test_save_rejects_identity_revision_and_mutated_nested_values(ready: SceneCard, tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    saved = save_scene(ready, path, now=NOW)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="identity"):
        save_scene(create_scene(now=NOW), path, now=NOW)
    data = document(saved)
    data["canvas"]["width"] = 200
    with pytest.raises(ValueError, match="new content revision"):
        save_scene(SceneCard.model_validate(data), path, now=NOW)
    ready.canvas.width = -1
    with pytest.raises(ValidationError):
        save_scene(ready, path, now=NOW)
    assert path.read_bytes() == before


def test_missing_thumbnail_retains_card_and_reports_dependency(ready: SceneCard, tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    card = save_scene(rendered(ready), path, asset_contents={"image": b"i", "prov": b"p", "thumb": b"t"}, now=NOW)
    asset_path(path, card.assets["thumb"]).unlink()
    reopened = load_scene(path)
    assert reopened.thumbnail_asset_id == "thumb"
    assert any(p.asset_id == "thumb" and p.code == "missing" for p in dependency_issues(reopened, path))
    assert save_scene(edit_scene(reopened, {"title": "renamed"}), path, now=NOW).renders == card.renders


def test_discovery_thumbnail_attribution_and_duplicate(tmp_path: Path) -> None:
    data = document(create_scene(now=NOW))
    data.update(assets={"d": {"kind": "discovery_thumbnail", "path": "thumb.png",
                              "source_url": "https://example.org/image", "credit": "Source credit"}},
                thumbnail_asset_id="d")
    path = tmp_path / "scene.json"
    card = save_scene(SceneCard.model_validate(data), path, asset_contents={"d": b"thumb"}, now=NOW)
    copied = duplicate_scene(card, path, tmp_path / "copy.json", now=NOW)
    assert copied.thumbnail_asset_id == "d"
    assert copied.assets["d"].source_url == card.assets["d"].source_url
    assert copied.assets["d"].credit == "Source credit"


def test_aliases_and_self_references_rejected(tmp_path: Path) -> None:
    data = document(create_scene(now=NOW))
    data["assets"] = {"a": {"kind": "source", "path": "a/../scene.json"}}
    with pytest.raises(ValidationError):
        SceneCard.model_validate(data)
    data["assets"] = {"a": {"kind": "source", "path": "scene.json"}}
    with pytest.raises(ValueError, match="itself"):
        save_scene(SceneCard.model_validate(data), tmp_path / "scene.json", now=NOW)
    data["assets"] = {key: {"kind": "source", "path": "same.bin"} for key in ("a", "b")}
    with pytest.raises(ValueError, match="alias"):
        save_scene(SceneCard.model_validate(data), tmp_path / "scene.json", now=NOW)


def test_new_history_cannot_reuse_missing_old_binary(ready: SceneCard, tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    card = save_scene(rendered(ready), path, asset_contents={"image": b"i", "prov": b"p", "thumb": b"t"}, now=NOW)
    asset_path(path, card.assets["image"]).unlink()
    data = document(card)
    other = dict(data["renders"][0])
    other["render_id"] = "second-run"
    data["renders"].append(other)
    with pytest.raises(ValueError, match="available binary"):
        save_scene(SceneCard.model_validate(data), path, now=NOW)


def test_invalid_load_logs_field_diagnostics(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "scene.json"
    data = document(create_scene(now=NOW))
    data["canvas"] = {"width": -1}
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        load_scene(path)
    assert "canvas.width" in caplog.text
    assert "greater_than" in caplog.text


def test_readiness_rejects_unknown_actions_and_context(ready: SceneCard) -> None:
    with pytest.raises(ValueError, match="unknown action"):
        readiness(ready, "other")
    with pytest.raises(ValueError, match="unknown branch"):
        readiness(ready, "render", branch="other")
    with pytest.raises(ValueError, match="plane_filters"):
        readiness(ready, "render", plane_filters={"": "F200W"})
    assert readiness(ready, "render", plane_filters={})


def test_ready_ratio_and_missing_operand(ready: SceneCard) -> None:
    mapping = document(ready)["mapping"]
    mapping["derived_planes"] = [{"name": "ratio", "operation": "ratio",
                                 "numerator": [{"plane": "p", "weight": 1}],
                                 "denominator": [{"plane": "p", "weight": 1}], "epsilon": 0.001}]
    mapping["planes"].append({"plane": "ratio", "rgb": {"red": 1, "green": 0, "blue": 0}})
    assert readiness(edit_scene(ready, {"mapping": mapping}), "render", plane_filters={"p": "F200W"}) == []
    mapping["derived_planes"][0].pop("denominator")
    assert readiness(edit_scene(ready, {"mapping": mapping}), "render", plane_filters={"p": "F200W"})


def test_scene_card_module_has_no_yaml_runtime_import() -> None:
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c",
        "import sys; import galaxy.scene_card; assert 'yaml' not in sys.modules; assert 'galaxy.config' not in sys.modules"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_save_scene_expected_previous_rejects_intervening_change(tmp_path: Path) -> None:
    path = tmp_path / "scene.json"
    original = save_scene(create_scene("Original", now=NOW), path, now=NOW)
    intervening = save_scene(
        edit_scene(original, {"title": "Intervening"}),
        path,
        now="2026-09-11T12:01:00Z",
    )
    stale = edit_scene(original, {"description": "stale"})

    with pytest.raises(ValueError, match="changed since it was read"):
        save_scene(
            stale,
            path,
            expected_previous=original,
            now="2026-09-11T12:02:00Z",
        )

    assert load_scene(path) == intervening


def test_pillars_library_example_is_valid_without_untracked_artifacts() -> None:
    from galaxy.scene_workflow import list_scene_library

    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "artifacts" / "Pillars.json"
    card = load_scene(path)
    assert card.title == "Pillars of Creation"
    assert len(card.selection.products or []) == 6
    assert len(card.selection.selected_product_ids or []) == 6
    assert sorted(product.filter for product in card.selection.products or []) == [
        "F090W", "F200W", "F444W", "F502N", "F657N", "F673N",
    ]
    assert all(product.data_uri for product in card.selection.products or [])
    assert card.assets is None
    assert dependency_issues(card, path) == []
    assert "yaml" not in path.read_text(encoding="utf-8").lower()

    entries = {entry.path.name: entry for entry in list_scene_library(path.parent)}
    assert entries["Pillars.json"].card == card
    assert entries["Pillars.json"].error is None

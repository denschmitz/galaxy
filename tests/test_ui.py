from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from galaxy.scene_card import append_render, create_scene, document, edit_scene, load_scene, save_scene
from galaxy.scene_models import Asset, SceneCard
from galaxy.scene_workflow import (
    LibraryOrigin, Screen, apply_manifest_selection, classify_input, default_scene_path,
    discover_workspace_inputs, draft_from_resolver_match, draft_from_target, duplicate_library_scene,
    export_current_render, initialize_canvas, inspect_scene_artifacts, list_project_library,
    list_scene_library, matching_render,
    manifest_from_card, materialize_render_defaults, recommended_rgb, render_issues, resize_canvas,
    merge_render_completion, resolve_workdir_input, save_draft, save_example_as_user_scene,
)
from galaxy.targeting import ResolverMatch
from galaxy.selection import CandidateManifest, CandidateRecord


NOW = "2026-09-14T12:00:00Z"


def candidate(identifier: str, filter_name: str, selected: bool = True) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=identifier, obsid="1", obs_id="obs-1",
        product_filename=f"{identifier}.fits", data_uri=f"mast:{identifier}",
        mission="JWST", instrument="NIRCAM", detector="NRCA1",
        filter_name=filter_name, product_type="SCIENCE", product_version="1",
        observation_date_start=None, observation_date_end=None, exposure_time=30.0,
        file_size=100, proposal_id=None, proposal_title=None, target_name=None,
        selection_rank=[], selected=selected,
    )


def manifest(*items: CandidateRecord) -> CandidateManifest:
    return CandidateManifest(
        generated_at=NOW, config_path=None, selection_policy="deepest_per_filter",
        max_observations_per_filter=1, candidates=list(items),
    )


def ready_card() -> SceneCard:
    card = draft_from_target(
        name="Fixture", ra_deg=12.0, dec_deg=-10.0,
        width_arcmin=2.0, height_arcmin=1.0,
    )
    card = apply_manifest_selection(
        card, manifest(candidate("mast:a", "F090W"), candidate("mast:b", "F444W"))
    )
    return materialize_render_defaults(card)


def rendered_card(tmp_path: Path) -> tuple[SceneCard, Path]:
    card = ready_card()
    card_path = tmp_path / "ready.scene.json"
    source = tmp_path / "assets" / "preview.png"
    provenance = tmp_path / "assets" / "provenance.json"
    source.parent.mkdir()
    Image.new("RGB", (4, 3), (10, 20, 30)).save(source)
    provenance.write_bytes(b"{}")
    card = append_render(
        card, snapshot=card, branch="original",
        plane_filters={"mast:a": "F090W", "mast:b": "F444W"},
        image_asset_id="image", provenance_asset_id="provenance",
        assets={
            "image": Asset(kind="render_image", path="assets/preview.png"),
            "provenance": Asset(kind="provenance", path="assets/provenance.json"),
        }, now=NOW,
    )
    return save_scene(card, card_path), card_path


def test_input_routing_rejects_yaml_and_routes_supported_artifacts(tmp_path: Path) -> None:
    card_path = tmp_path / "scene.json"
    save_scene(create_scene(now=NOW), card_path, now=NOW)
    route = classify_input(card_path)
    assert (route.kind, route.screen) == ("scene", Screen.REFINEMENT)
    yaml_path = tmp_path / "project.yaml"
    yaml_path.write_text("format_revision: 1")
    with pytest.raises(ValueError, match="must be"):
        classify_input(yaml_path)
    fits = tmp_path / "exported_planes.fits"
    fits.write_bytes(b"FITS")
    assert classify_input(fits).screen == Screen.RENDER


def test_streamlit_normal_launch_opens_discovery() -> None:
    source = (
        "import sys\n"
        "sys.argv = ['ui.py']\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    assert not app.exception
    assert "Discovery" in [item.value for item in app.title]
    assert "Latest JWST releases" in [item.label for item in app.tabs]
    assert any("Operation: idle" in item.value for item in app.caption)


def test_streamlit_file_entrypoint_invokes_main() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "galaxy" / "ui.py"
    source = (
        "import runpy, sys\n"
        "sys.argv = ['ui.py']\n"
        f"runpy.run_path({str(path)!r}, run_name='__main__')\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    assert not app.exception
    assert "Discovery" in [item.value for item in app.title]
    assert "Open Saved scenes" in [item.label for item in app.button]


def test_streamlit_normal_launch_opens_pillars_example_and_inventory() -> None:
    source = (
        "import sys\n"
        "sys.argv = ['ui.py']\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    assert "Projects and scenes" in [item.value for item in app.title]
    assert "Examples" in [item.value for item in app.header]
    assert "Pillars of Creation" in [item.value for item in app.subheader]
    captions = [item.value for item in app.caption]
    assert any("Bundled example" in value and "Render ready" in value for value in captions)
    next(button for button in app.button if button.label == "Open").click().run(timeout=20)
    assert "Scene refinement" in [item.value for item in app.title]
    assert "Artifacts" in [item.label for item in app.tabs]
    assert "Save as new scene" in [item.label for item in app.button]
    body = [item.value for item in app.markdown]
    assert "Selected source products: 6" in body
    assert "Remote-only downloadable sources: 6" in body
    assert "Missing or corrupt referenced assets: 0" in body


def test_streamlit_controls_commit_after_one_activation() -> None:
    source = (
        "import sys\n"
        "sys.argv = ['ui.py']\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    region = next(item for item in app.radio if item.label == "Region")
    app = region.set_value("circle").run(timeout=20)
    assert next(item for item in app.radio if item.label == "Region").value == "circle"
    assert "Radius (arcmin)" in [item.label for item in app.number_input]

    app = app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    assert "Projects and scenes" in [item.value for item in app.title]
    app = next(button for button in app.button if button.label == "Open").click().run(timeout=20)
    force = next(item for item in app.checkbox if item.label == "Force a new MAST query")
    app = force.set_value(True).run(timeout=20)
    assert next(
        item for item in app.checkbox if item.label == "Force a new MAST query"
    ).value is True

    app = app.sidebar.radio[0].set_value(Screen.OUTPUT.value).run(timeout=20)
    output_format = next(item for item in app.radio if item.label == "Format")
    app = output_format.set_value("tiff").run(timeout=20)
    assert next(item for item in app.radio if item.label == "Format").value == "tiff"


def test_manifest_and_workdir_routing(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(manifest(candidate("a", "F090W")).to_dict()))
    assert classify_input(path).kind == "manifest"
    assert resolve_workdir_input(tmp_path).path == path.resolve()


def test_normal_workspace_discovery_lists_without_opening(tmp_path: Path) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    scene = examples / "choice.scene.json"
    save_scene(create_scene(now=NOW), scene, now=NOW)
    choices = discover_workspace_inputs(tmp_path)
    assert [(item.kind, item.path) for item in choices] == [("scene", scene.resolve())]


def test_target_draft_initializes_required_default_canvas() -> None:
    card = draft_from_target(
        name="Horsehead", ra_deg=85.25, dec_deg=-2.4,
        width_arcmin=2.1, height_arcmin=1.2,
    )
    assert card.canvas.width == 126
    assert card.canvas.height == 72
    assert card.canvas.pixel_scale_arcsec == 1.0
    assert card.canvas.rotation_deg == 0.0
    assert card.canvas.center.ra_deg == 85.25


def test_canvas_requires_resolved_region_and_preserves_existing_frame() -> None:
    card = draft_from_target(name="Unresolved", width_arcmin=2.0, height_arcmin=2.0)
    with pytest.raises(ValueError, match="resolved coordinates"):
        initialize_canvas(card)
    ready = ready_card()
    assert initialize_canvas(ready) is ready


def test_manifest_application_pins_exact_products_and_observation() -> None:
    card = draft_from_target(
        ra_deg=1.0, dec_deg=2.0, width_arcmin=1.0, height_arcmin=1.0
    )
    updated = apply_manifest_selection(
        card, manifest(candidate("exact-1", "F200W"),
                       candidate("exact-2", "F444W", False))
    )
    assert updated.selection.selected_product_ids == ["exact-1"]
    assert [product.product_id for product in updated.selection.products] == ["exact-1", "exact-2"]
    assert updated.selection.observation_ids == ["obs-1"]
    assert updated.planes.enabled_filters == ["F200W"]
    restored = manifest_from_card(updated)
    assert [item.candidate_id for item in restored.candidates if item.selected] == ["exact-1"]


def test_defaults_are_explicit_and_wavelength_ordered() -> None:
    weights = recommended_rgb(["F444W", "F502N", "F090W"])
    assert weights["F502N"]["blue"] > weights["F444W"]["blue"]
    card = ready_card()
    assert not render_issues(card)
    assert card.mapping.defaults.strategy == "continuum"
    assert card.tone.percentiles.black == 1.0
    assert card.psf.enabled is False


def test_mapping_change_makes_previous_render_stale(tmp_path: Path) -> None:
    card, _ = rendered_card(tmp_path)
    assert matching_render(card) is not None
    mapping = document(card.mapping)
    mapping["planes"][0]["rgb"]["red"] = 0.25
    changed = edit_scene(card, {"mapping": mapping})
    assert matching_render(changed) is None


def test_render_completion_preserves_newer_live_inputs_and_adds_stale_history(tmp_path: Path) -> None:
    completed, path = rendered_card(tmp_path)
    mapping = document(completed.renders[0].inputs.mapping)
    mapping["planes"][0]["rgb"]["red"] = 0.125
    live_data = document(completed.renders[0].inputs)
    base = SceneCard.model_validate({
        **{key: value for key, value in document(completed).items()
           if key not in {"renders", "assets", "thumbnail_asset_id"}},
        **live_data,
    })
    live = edit_scene(base, {"mapping": mapping})
    merged = merge_render_completion(live, completed)
    assert merged.content_revision == live.content_revision
    assert document(merged.mapping) == mapping
    assert len(merged.renders) == 1
    assert matching_render(merged) is None
    assert merged.thumbnail_asset_id is None
    committed = save_scene(merged, path)
    assert load_scene(path) == committed
    assert document(committed.mapping) == mapping


def test_render_completion_rejects_another_scene() -> None:
    with pytest.raises(ValueError, match="different scene"):
        merge_render_completion(ready_card(), ready_card())


def test_resize_preserves_extent_and_rejects_aspect_change() -> None:
    card = ready_card()
    resized = resize_canvas(card, card.canvas.width * 2, card.canvas.height * 2)
    assert resized.canvas.pixel_scale_arcsec == card.canvas.pixel_scale_arcsec / 2
    with pytest.raises(ValueError, match="aspect ratio"):
        resize_canvas(card, card.canvas.width * 2, card.canvas.height)


def test_scene_library_isolates_invalid_cards(tmp_path: Path) -> None:
    save_scene(create_scene("Valid", now=NOW), tmp_path / "valid.json", now=NOW)
    (tmp_path / "broken.json").write_text('{"document_type":"galaxy.scene_card"}')
    (tmp_path / "manifest.json").write_text('{"candidates":[]}')
    entries = list_scene_library(tmp_path)
    assert len(entries) == 2
    assert {entry.readiness_label for entry in entries} == {"Draft", "Invalid"}


def test_library_reports_missing_thumbnail_dependency(tmp_path: Path) -> None:
    data = document(create_scene("Missing thumb", now=NOW))
    data["assets"] = {
        "thumb": {"kind": "discovery_thumbnail", "path": "missing.png",
                  "source_url": "https://example.test/source"}
    }
    data["thumbnail_asset_id"] = "thumb"
    card = SceneCard.model_validate(data)
    # Existing missing dependencies may be reopened, so publish the fixture JSON directly.
    (tmp_path / "missing.json").write_text(json.dumps(document(card)))
    entry = list_scene_library(tmp_path)[0]
    assert entry.card is not None
    assert entry.thumbnail_kind == "placeholder"
    assert entry.dependencies[0].asset_id == "thumb"


def test_project_library_separates_example_and_user_scenes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    examples = project / "artifacts"
    users = tmp_path / "users"
    examples.mkdir(parents=True)
    users.mkdir()
    example_path = examples / "Pillars.json"
    example = save_scene(create_scene("Pillars", now=NOW), example_path, now=NOW)
    save_scene(create_scene("Personal", now=NOW), users / "personal.json", now=NOW)
    library = list_project_library(users, project)
    assert [entry.card.title for entry in library.examples] == ["Pillars"]
    assert [entry.card.title for entry in library.saved_scenes] == ["Personal"]
    assert library.examples[0].origin is LibraryOrigin.BUNDLED_EXAMPLE
    # A case-equivalent configured path and the same stable identity are shown once.
    duplicate = users / "PILLARS.json"
    duplicate.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    library = list_project_library(examples, project)
    assert len(library.examples) == 1
    assert not library.saved_scenes
    assert library.examples[0].card.scene_id == example.scene_id


def test_pillars_inventory_is_remote_only_and_ignores_unreferenced_files(tmp_path: Path) -> None:
    source = Path("artifacts/Pillars.json").resolve()
    path = tmp_path / "artifacts" / "Pillars.json"
    path.parent.mkdir()
    path.write_bytes(source.read_bytes())
    card = load_scene(path)
    clean_inventory = inspect_scene_artifacts(card, path)
    unrelated = path.parent / "Pillars" / "unreferenced.fits"
    unrelated.parent.mkdir()
    unrelated.write_bytes(b"not an artifact")
    inventory = inspect_scene_artifacts(card, path)
    assert inventory == clean_inventory
    assert len(inventory.sources) == 6
    assert inventory.remote_source_count == 6
    assert inventory.local_source_count == 0
    assert inventory.asset_count("candidate_manifest") == 0
    assert inventory.asset_count("aligned_planes") == 0
    assert len(inventory.renders) == 0
    assert inventory.export_count == 0
    assert inventory.issue_count == 0
    assert {item.filter_name for item in inventory.sources} == {
        "F090W", "F200W", "F444W", "F502N", "F657N", "F673N"
    }


def test_inventory_distinguishes_missing_and_corrupt_sources(tmp_path: Path) -> None:
    base = ready_card()
    data = document(base)
    data["selection"]["products"][0]["cached_asset_id"] = "missing-source"
    data["selection"]["products"][1]["cached_asset_id"] = "bad-source"
    data["assets"] = {
        "missing-source": {"kind": "source", "path": "assets/missing.fits"},
        "bad-source": {
            "kind": "source", "path": "assets/bad.fits",
            "sha256": "0" * 64,
        },
    }
    card = SceneCard.model_validate(data)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "bad.fits").write_bytes(b"wrong")
    inventory = inspect_scene_artifacts(card, tmp_path / "scene.json")
    assert [item.status for item in inventory.sources] == ["missing", "corrupt"]
    assert inventory.issue_count == 2


def test_inventory_distinguishes_current_and_stale_render(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    assert [item.state for item in inspect_scene_artifacts(card, path).renders] == ["current"]
    mapping = document(card.mapping)
    mapping["planes"][0]["rgb"]["red"] = 0.2
    changed = edit_scene(card, {"mapping": mapping})
    assert [item.state for item in inspect_scene_artifacts(changed, path).renders] == ["stale"]


def test_example_save_creates_new_identity_without_modifying_source(tmp_path: Path) -> None:
    path = Path("artifacts/Pillars.json").resolve()
    before = path.read_bytes()
    original = load_scene(path)
    changed = edit_scene(original, {"title": "Edited Pillars"})
    saved, destination = save_example_as_user_scene(changed, tmp_path)
    assert destination.parent == tmp_path.resolve()
    assert saved.scene_id != original.scene_id
    assert saved.title == "Edited Pillars"
    assert path.read_bytes() == before


def test_save_uses_scene_directory_and_duplicate_has_new_identity(tmp_path: Path) -> None:
    card = create_scene("Cool Scene", now=NOW)
    saved, path = save_draft(card, tmp_path)
    assert path == default_scene_path(card, tmp_path)
    entry = next(item for item in list_scene_library(tmp_path) if item.card)
    copied, copied_path = duplicate_library_scene(entry, tmp_path)
    assert copied.scene_id != saved.scene_id
    assert copied_path != path
    assert copied.title == "Cool Scene copy"
    assert not copied_path.exists()
    assert copied.renders is None


def test_resolver_match_draft_records_identity_and_source() -> None:
    card = draft_from_resolver_match(
        "M1", ResolverMatch("Messier 1", 83.633, 22.014), "fixture-resolver",
        region_size_arcmin=3.0,
    )
    assert card.target.name == "M1"
    assert card.target.resolved_name == "Messier 1"
    assert card.target.ra_deg == pytest.approx(83.633)
    source = card.discovery.sources[0]
    assert source.source_kind == "name_resolver"
    assert source.extracted_metadata["resolver"] == "fixture-resolver"


def test_export_requires_current_render_and_explicit_overwrite(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    output = tmp_path / "exports" / "image"
    exported = export_current_render(card, path, output, output_format="png")
    final = output.with_suffix(".png")
    with Image.open(final) as image:
        assert image.format == "PNG"
    assert exported.exports[-1].destination == str(final.resolve())
    with pytest.raises(FileExistsError):
        export_current_render(exported, path, final, output_format="png")
    assert len(load_scene(path).exports) == 1


def test_tiff_export_contains_tiff_data(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    output = tmp_path / "exports" / "image.tiff"
    export_current_render(card, path, output, output_format="tiff")
    with Image.open(output) as image:
        assert image.format == "TIFF"


def test_export_rejects_stale_or_unrendered_scene(tmp_path: Path) -> None:
    card = ready_card()
    path = tmp_path / "draft.json"
    save_scene(card, path)
    with pytest.raises(ValueError, match="current successful render"):
        export_current_render(card, path, tmp_path / "out.png", output_format="png")

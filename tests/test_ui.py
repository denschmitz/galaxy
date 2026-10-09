from __future__ import annotations

import json
from pathlib import Path

import pytest
import numpy as np
from PIL import Image
from astropy.io import fits
from astropy.wcs import WCS
from streamlit.testing.v1 import AppTest
from tifffile import imread, imwrite

from galaxy.scene_card import append_render, create_scene, document, edit_scene, load_scene, save_scene
from galaxy.scene_models import Asset, SceneCard
from galaxy.processing_config import NormalizationReferenceConfig
from galaxy.planes import export_multiplane_fits
from galaxy.reprojection import ReprojectedPlane
from galaxy.scene_workflow import (
    LibraryOrigin, Screen, apply_manifest_selection, classify_input, default_scene_path,
    discover_workspace_inputs, draft_from_resolver_match, draft_from_target, duplicate_library_scene,
    example_user_path, export_current_render, initialize_canvas, inspect_scene_artifacts, list_project_library,
    list_scene_library, matching_render,
    manifest_from_card, materialize_example, materialize_render_defaults, open_example_user_copy,
    recommended_rgb, render_issues, resize_canvas,
    merge_render_completion, resolve_workdir_input, save_draft,
)
from galaxy.targeting import ResolverMatch
from galaxy.ui import (
    _current_footprint_path,
    _mapping_with_reference_bounds,
    _render_launch_needs_save,
    _single_main_stretch,
)
from galaxy.selection import CandidateManifest, CandidateRecord


NOW = "2026-09-14T12:00:00Z"


def test_mapping_reference_apply_expands_filter_selector_to_locked_plane_bounds() -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
    plane = ReprojectedPlane(
        "plane-a", np.arange(4, dtype=np.float32).reshape(2, 2),
        np.ones((2, 2), dtype=np.float32), {"filter": "F090W"}, wcs=wcs,
    )
    reference = NormalizationReferenceConfig(
        reference_id="ref", region_ids=["sky"], branch="original", grid_id=plane.grid_id,
        source_ids=list(plane.source_ids), coverage_policy="available_contributors",
        black_percentile=1.0, white_percentile=99.0, black_value=0.25, white_value=2.75,
        sample_count=4, low_clipping_fraction=0.25, high_clipping_fraction=0.25,
    )

    result = _mapping_with_reference_bounds(
        {"planes": [{"filter": "F090W", "rgb": {"red": 0, "green": 0, "blue": 1}}]},
        [plane], {"plane-a": reference},
    )

    assert result["planes"][0]["plane"] == "plane-a"
    assert "filter" not in result["planes"][0]
    assert result["planes"][0]["normalization"]["mode"] == "fixed_bounds"
    assert result["planes"][0]["normalization"]["reference"]["locked"] is True


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


def test_new_scene_defaults_to_union_output_with_common_overlap_tone_reference() -> None:
    card = ready_card()

    assert card.coverage.policy == "available_contributors"
    assert card.coverage.tone_reference == "common_required_bands"
    assert card.coverage.crop == "none"


def test_single_main_stretch_is_explicit_and_does_not_mutate_input_recipe() -> None:
    card = ready_card()
    mapping_before = document(card.mapping)
    tone_before = document(card.tone)

    mapping, tone = _single_main_stretch(mapping_before, tone_before)

    assert mapping["defaults"]["normalization"]["stretch"] == "linear"
    assert tone["application"] == "shared_intensity"
    assert tone["shared_stretch"] == {"kind": "asinh", "parameter": 4.0}
    assert mapping_before["defaults"]["normalization"]["stretch"] == "asinh"
    assert "application" not in tone_before


def test_streamlit_phase5_tone_controls_and_single_main_stretch(tmp_path: Path) -> None:
    _, card_path = rendered_card(tmp_path)
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', {str(card_path)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    app = app.sidebar.radio[0].set_value(Screen.RENDER.value).run(timeout=20)
    assert "Tone application" in [item.label for item in app.selectbox]
    labels = [button.label for button in app.button]
    assert "Use single main stretch" in labels
    assert "Preview auto-stretch proposal" in labels
    assert "Apply auto-stretch proposal" in labels

    app = next(
        button for button in app.button if button.label == "Use single main stretch"
    ).click().run(timeout=20)
    active = app.session_state["active_card"]
    assert active.tone.application == "shared_intensity"
    assert active.tone.shared_stretch.kind == "asinh"
    assert active.mapping.defaults.normalization.stretch == "linear"
    assert matching_render(active) is None


def test_applied_auto_stretch_values_save_and_reopen_without_reestimation(tmp_path: Path) -> None:
    card = ready_card()
    tone = document(card.tone)
    tone.update({
        "application": "shared_intensity",
        "shared_stretch": {"kind": "asinh", "parameter": 12.5},
        "gamut_policy": "rescale",
        "auto_stretch": {
            "algorithm_version": "autostretch-shared-asinh-v1",
            "reference_id": "background-key", "branch": "original",
            "grid_id": "grid-a", "source_ids": ["source-a"],
            "sample_count": 4096, "source_median": 0.025,
            "robust_spread": 0.002, "object_fraction": 0.01,
            "target_median": 0.1, "resolved_parameter": 12.5,
            "low_clipping_fraction": 0.0, "high_clipping_fraction": 0.001,
            "confidence": "high", "locked": True,
        },
    })
    changed = edit_scene(card, {"tone": tone})
    path = tmp_path / "auto.scene.json"
    save_scene(changed, path, now=changed.updated_at)

    reopened = load_scene(path)

    assert document(reopened.tone) == tone
    assert reopened.tone.auto_stretch.resolved_parameter == 12.5


def rendered_card(tmp_path: Path) -> tuple[SceneCard, Path]:
    card = ready_card()
    mapping = document(card.mapping)
    for entry in mapping["planes"]:
        entry["rgb"] = {"red": 1.0, "green": 1.0, "blue": 1.0}
    card = edit_scene(card, {"mapping": mapping})
    card_path = tmp_path / "ready.scene.json"
    source = tmp_path / "assets" / "preview.png"
    high_depth = tmp_path / "assets" / "preview.tiff"
    provenance = tmp_path / "assets" / "provenance.json"
    aligned = tmp_path / "assets" / "aligned-planes.fits"
    source.parent.mkdir()
    gradient = np.linspace(0, 65535, 1024, dtype=np.uint16).reshape(32, 32)
    high_depth_rgb = np.stack((gradient, gradient, gradient), axis=-1)
    Image.fromarray((high_depth_rgb / 257).astype(np.uint8), mode="RGB").save(source)
    imwrite(high_depth, high_depth_rgb, photometric="rgb")
    provenance.write_bytes(b"{}")
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [12.0, -10.0]
    wcs.wcs.crpix = [16.5, 16.5]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]
    yy, xx = np.indices((32, 32), dtype=np.float32)
    coverage = np.ones((32, 32), dtype=np.float32)
    export_multiplane_fits([
        ReprojectedPlane(
            "mast:a", 10.0 + xx / 100.0, coverage,
            {"filter": "F090W", "native_unit": "MJy/sr", "artifact_branch": "original"},
            wcs=wcs, branch="original", source_ids=("mast:a",), parent_ids=("mast:a",),
        ),
        ReprojectedPlane(
            "mast:b", 20.0 + yy / 100.0, coverage,
            {"filter": "F444W", "native_unit": "MJy/sr", "artifact_branch": "original"},
            wcs=wcs, branch="original", source_ids=("mast:b",), parent_ids=("mast:b",),
        ),
    ], aligned)
    card = append_render(
        card, snapshot=card, branch="original",
        plane_filters={"mast:a": "F090W", "mast:b": "F444W"},
        image_asset_id="image", provenance_asset_id="provenance",
        high_depth_image_asset_id="high-depth",
        aligned_plane_asset_ids=["aligned"],
        assets={
            "image": Asset(kind="render_image", path="assets/preview.png"),
            "high-depth": Asset(kind="render_image", path="assets/preview.tiff"),
            "provenance": Asset(kind="provenance", path="assets/provenance.json"),
            "aligned": Asset(kind="aligned_planes", path="assets/aligned-planes.fits"),
        }, now=NOW,
    )
    return save_scene(card, card_path), card_path


def background_ready_card(tmp_path: Path) -> tuple[SceneCard, Path]:
    return rendered_card(tmp_path)


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


def test_streamlit_background_preview_apply_and_disable_workflow(tmp_path: Path) -> None:
    _, card_path = background_ready_card(tmp_path)
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', {str(card_path)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    app = app.sidebar.radio[0].set_value(Screen.RENDER.value).run(timeout=20)
    labels = [button.label for button in app.button]
    assert "Preview pedestal proposal" in labels
    assert "Apply pedestal proposal" in labels
    assert "Disable background correction" in labels

    app = next(
        button for button in app.button if button.label == "Preview pedestal proposal"
    ).click().run(timeout=20)
    assert app.session_state["background_proposal"]["branch"] == "original"
    assert len(app.dataframe) == 1
    assert not [item.value for item in app.warning if "Candidate rendering" in item.value]

    app = next(
        button for button in app.button if button.label == "Apply pedestal proposal"
    ).click().run(timeout=20)
    active = app.session_state["active_card"]
    assert active.background.mode == "pedestal"
    assert active.background.black_reference_policy == "corrected_zero"
    assert set(active.background.resolved_branches["original"]) == {"mast:a", "mast:b"}
    assert matching_render(active) is None


def test_streamlit_normal_launch_opens_materialized_pillars_and_inventory(tmp_path: Path) -> None:
    scene_directory = tmp_path / "scenes"
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(scene_directory)!r}]\n"
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
    assert (scene_directory / "Pillars.json").is_file()
    assert "Scene refinement" in [item.value for item in app.title]
    assert "Artifacts" in [item.label for item in app.tabs]
    assert "Save draft" in [item.label for item in app.button]
    assert "Save as new scene" not in [item.label for item in app.button]
    body = [item.value for item in app.markdown]
    assert "Selected source products: 6" in body
    assert "Remote-only downloadable sources: 6" in body
    assert "Missing or corrupt referenced assets: 0" in body


def test_streamlit_example_duplicate_confirms_json_only_overwrite(tmp_path: Path) -> None:
    scene_directory = tmp_path / "scenes"
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(scene_directory)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    app = app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    app = next(button for button in app.button if button.label == "Duplicate").click().run(timeout=20)
    destination = scene_directory / "Pillars.json"
    assert destination.is_file()
    asset = scene_directory / "Pillars" / "retained.fits"
    asset.parent.mkdir()
    asset.write_bytes(b"retained")
    user_data = json.loads(destination.read_text(encoding="utf-8"))
    user_data["title"] = "User title"
    destination.write_text(json.dumps(user_data), encoding="utf-8")
    before = destination.read_bytes()

    app = app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    app = next(button for button in app.button if button.label == "Duplicate").click().run(timeout=20)
    assert "Overwrite user scene JSON" in [button.label for button in app.button]
    app = next(
        button for button in app.button if button.label == "Cancel overwrite"
    ).click().run(timeout=20)
    assert destination.read_bytes() == before
    assert asset.read_bytes() == b"retained"

    app = next(button for button in app.button if button.label == "Duplicate").click().run(timeout=20)
    app = next(
        button for button in app.button if button.label == "Overwrite user scene JSON"
    ).click().run(timeout=20)
    assert destination.read_bytes() == Path("examples/Pillars.json").read_bytes()
    assert asset.read_bytes() == b"retained"


def test_streamlit_saved_project_delete_requires_confirmation_and_is_recoverable(
    tmp_path: Path,
) -> None:
    scene_directory = tmp_path / "scenes"
    scene_directory.mkdir()
    card_path = scene_directory / "horsehead.scene.json"
    save_scene(create_scene("Horsehead Nebula", now=NOW), card_path, now=NOW)
    asset_root = scene_directory / "horsehead.assets"
    asset_root.mkdir()
    (asset_root / "preview.png").write_bytes(b"preview")
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(scene_directory)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    app = app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    assert [button.label for button in app.button].count("Delete") == 1

    app = next(button for button in app.button if button.label == "Delete").click().run(timeout=20)
    assert "Delete project" in [button.label for button in app.button]
    assert card_path.is_file()
    app = next(button for button in app.button if button.label == "Cancel").click().run(timeout=20)
    assert card_path.is_file()

    app = [button for button in app.button if button.label == "Open"][-1].click().run(timeout=20)
    assert app.session_state["active_path"] == card_path.resolve()
    app = app.sidebar.radio[0].set_value(Screen.LIBRARY.value).run(timeout=20)
    app = next(button for button in app.button if button.label == "Delete").click().run(timeout=20)
    app = next(
        button for button in app.button if button.label == "Delete project"
    ).click().run(timeout=20)
    assert not card_path.exists()
    assert not asset_root.exists()
    trash = scene_directory / ".galaxy-trash"
    assert any((transaction / card_path.name).is_file() for transaction in trash.iterdir())
    assert any((transaction / asset_root.name / "preview.png").is_file() for transaction in trash.iterdir())
    assert any("Recovery files:" in item.value for item in app.success)
    assert app.session_state["active_card"] is None


def test_streamlit_fit_selected_scans_previews_before_apply(tmp_path: Path) -> None:
    scene_directory = tmp_path / "scenes"
    scene_directory.mkdir()
    card_path = scene_directory / "fit.scene.json"
    card = ready_card()
    card_data = document(card)
    card_data["selection"]["products"][0]["filename"] = "a.fits"
    card_data["selection"]["products"][1]["filename"] = "b.fits"
    card = SceneCard.model_validate(card_data)
    save_scene(card, card_path)
    cache = scene_directory / "fit.assets" / "render-old" / "cache"
    cache.mkdir(parents=True)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [12.0, -10.0]
    wcs.wcs.crpix = [10.0, 10.0]
    wcs.wcs.cdelt = [-0.5 / 3600.0, 0.5 / 3600.0]
    header = wcs.to_header()
    for filename, filter_name in (("a.fits", "F090W"), ("b.fits", "F444W")):
        local_header = header.copy()
        local_header["FILTER"] = filter_name
        fits.PrimaryHDU(
            data=np.ones((20, 20), dtype=np.float32), header=local_header,
        ).writeto(cache / filename)
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', {str(card_path)!r}]\n"
        "from galaxy.ui import main\n"
        "main()\n"
    )
    app = AppTest.from_string(source, default_timeout=20).run(timeout=20)
    original_canvas = document(card.canvas)

    app = next(
        button for button in app.button if button.label == "Fit selected scans"
    ).click().run(timeout=20)
    assert not app.error, [item.value for item in app.error]
    assert "Fitted-frame preview" in [item.value for item in app.subheader]
    assert len(app.get("imgs")) == 1
    assert document(app.session_state["active_card"].canvas) == original_canvas

    app = next(
        button for button in app.button if button.label == "Apply fitted canvas"
    ).click().run(timeout=20)
    fitted = app.session_state["active_card"].canvas
    assert fitted.frame_origin == "selected_footprints"
    assert document(fitted) != original_canvas


def test_frame_uses_only_footprint_overlay_from_current_render(tmp_path: Path) -> None:
    card, card_path = rendered_card(tmp_path)
    footprint = tmp_path / "assets" / "footprints.png"
    Image.new("L", (4, 3), 255).save(footprint)
    data = document(card)
    data["assets"]["footprint"] = {
        "kind": "footprint", "path": "assets/footprints.png",
    }
    data["renders"][-1]["footprint_asset_id"] = "footprint"
    current = SceneCard.model_validate(data)

    assert _current_footprint_path(current, card_path) == footprint.resolve()

    canvas = document(current.canvas)
    canvas["rotation_deg"] = 12.0
    stale = edit_scene(current, {"canvas": canvas})
    assert _current_footprint_path(stale, card_path) is None

def test_streamlit_controls_commit_after_one_activation(tmp_path: Path) -> None:
    scene_directory = tmp_path / "scenes"
    source = (
        "import sys\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(scene_directory)!r}]\n"
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
    artifacts = tmp_path / "artifacts"
    examples.mkdir()
    artifacts.mkdir()
    example = examples / "choice.scene.json"
    scene = artifacts / "workspace.scene.json"
    save_scene(create_scene(now=NOW), example, now=NOW)
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
    assert restored.selection_mode == "custom"
    assert [item.candidate_id for item in restored.candidates if item.selected] == ["exact-1"]


def test_reduced_selection_recovers_local_sources_and_replaces_stale_defaults() -> None:
    card = draft_from_target(
        ra_deg=1.0, dec_deg=2.0, width_arcmin=1.0, height_arcmin=1.0,
    )
    full = manifest(candidate("hst-a", "F502N"), candidate("jwst-b", "F090W"))
    card = materialize_render_defaults(apply_manifest_selection(card, full))
    accepted_canvas = document(card.canvas)
    data = document(card)
    data["assets"] = {
        "source-hst-a": {"kind": "source", "path": "assets/hst-a.fits"},
        "source-jwst-b": {"kind": "source", "path": "assets/jwst-b.fits"},
    }
    # Reproduce an already affected clone: local assets exist but Apply previously
    # discarded cached_asset_id from both product records.
    for product in data["selection"]["products"]:
        product.pop("cached_asset_id", None)
    card = SceneCard.model_validate(data)
    reduced = manifest(
        candidate("hst-a", "F502N"), candidate("jwst-b", "F090W", False),
    )

    updated = apply_manifest_selection(card, reduced)
    updated = materialize_render_defaults(updated, replace_existing=True)

    products = {product.product_id: product for product in updated.selection.products}
    assert updated.selection.selected_product_ids == ["hst-a"]
    assert products["hst-a"].cached_asset_id == "source-hst-a"
    assert products["jwst-b"].cached_asset_id == "source-jwst-b"
    assert updated.planes.enabled_filters == ["F502N"]
    assert [entry.filter for entry in updated.mapping.planes] == ["F502N"]
    assert document(updated.canvas) == accepted_canvas
    assert updated.psf.enabled is False
    assert updated.background.mode == "off"
    assert not render_issues(updated)


def test_defaults_are_explicit_and_wavelength_ordered() -> None:
    weights = recommended_rgb(["F444W", "F502N", "F090W"])
    assert weights["F502N"]["blue"] > weights["F444W"]["blue"]
    card = ready_card()
    assert not render_issues(card)
    assert card.mapping.defaults.strategy == "continuum"
    assert card.mapping.defaults.normalization.mode == "percentile"
    assert card.mapping.defaults.normalization.black_percentile == 0.5
    assert card.mapping.defaults.normalization.white_percentile == 99.5
    assert card.mapping.defaults.normalization.stretch == "asinh"
    assert card.mapping.defaults.normalization.stretch_parameter == 4.0
    assert card.mapping.defaults.normalization.gain == 1.0
    assert card.tone.percentiles.black == 1.0
    assert card.psf.enabled is False


def test_render_launch_requires_save_when_live_scene_differs_from_disk() -> None:
    draft = draft_from_target(
        name="Render handoff", ra_deg=12.0, dec_deg=-10.0,
        width_arcmin=2.0, height_arcmin=1.0,
    )
    saved_document = document(draft)
    ready = apply_manifest_selection(
        draft, manifest(candidate("mast:a", "F090W"), candidate("mast:b", "F444W"))
    )
    ready = materialize_render_defaults(ready)

    assert _render_launch_needs_save(ready, Path("saved.scene.json"), saved_document)
    assert _render_launch_needs_save(ready, None, None)
    assert not _render_launch_needs_save(draft, Path("saved.scene.json"), saved_document)


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
    examples = project / "examples"
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
    # The materialized same-identity user copy remains visible as user-owned work.
    duplicate = users / "Pillars.json"
    duplicate.write_bytes(example_path.read_bytes())
    library = list_project_library(users, project)
    assert {entry.card.title for entry in library.saved_scenes} == {"Pillars", "Personal"}
    # A configured directory equal to the example source is path-deduplicated.
    library = list_project_library(examples, project)
    assert len(library.examples) == 1
    assert not library.saved_scenes
    assert library.examples[0].card.scene_id == example.scene_id


def test_pillars_inventory_is_remote_only_and_ignores_unreferenced_files(tmp_path: Path) -> None:
    source = Path("examples/Pillars.json").resolve()
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


def test_inventory_reports_units_masks_normalization_and_mixed_unit_warning(tmp_path: Path) -> None:
    card = ready_card()
    data = document(card)
    data["mapping"]["defaults"]["normalization"] = {
        "mode": "native",
        "black_percentile": 0.5,
        "white_percentile": 99.5,
        "stretch": "asinh",
        "stretch_parameter": 4.0,
        "gain": 1.0,
    }
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    for filename, unit, with_weight in (
        ("a.fits", "ELECTRONS/S", True),
        ("b.fits", "MJy/sr", False),
    ):
        primary = fits.PrimaryHDU(data=np.ones((2, 2), dtype=np.float32))
        primary.header["BUNIT"] = unit
        hdus = [primary]
        if with_weight:
            hdus.append(fits.ImageHDU(data=np.ones((2, 2), dtype=np.float32), name="WHT"))
        fits.HDUList(hdus).writeto(assets_dir / filename)
    for product, asset_id in zip(data["selection"]["products"], ("source-a", "source-b"), strict=True):
        product["cached_asset_id"] = asset_id
    data["assets"] = {
        "source-a": {"kind": "source", "path": "assets/a.fits"},
        "source-b": {"kind": "source", "path": "assets/b.fits"},
    }
    card = SceneCard.model_validate(data)

    inventory = inspect_scene_artifacts(card, tmp_path / "scene.json")

    assert [item.native_unit for item in inventory.sources] == ["ELECTRONS/S", "MJy/sr"]
    assert inventory.sources[0].mask_sources == ("WHT",)
    assert all(item.normalization_mode == "native" for item in inventory.sources)
    assert all(item.valid_coverage_fraction is None for item in inventory.sources)
    assert all(item.rgb_contribution_percent is None for item in inventory.sources)
    assert "Mixed native FITS units" in inventory.warnings[0]


def test_inventory_distinguishes_current_and_stale_render(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    assert [item.state for item in inspect_scene_artifacts(card, path).renders] == ["current"]
    mapping = document(card.mapping)
    mapping["planes"][0]["rgb"]["red"] = 0.2
    changed = edit_scene(card, {"mapping": mapping})
    assert [item.state for item in inspect_scene_artifacts(changed, path).renders] == ["stale"]


def test_example_materialization_preserves_filename_identity_and_source(tmp_path: Path) -> None:
    source = Path("examples/Pillars.json").resolve()
    before = source.read_bytes()
    original = load_scene(source)
    saved, destination = materialize_example(source, tmp_path)
    assert destination == tmp_path.resolve() / "Pillars.json"
    assert destination.read_bytes() == before
    assert saved.scene_id == original.scene_id
    assert source.read_bytes() == before
    assert not (tmp_path / "Pillars").exists()


def test_example_overwrite_requires_permission_and_retains_asset_root(tmp_path: Path) -> None:
    examples = tmp_path / "source"
    users = tmp_path / "users"
    examples.mkdir()
    source = examples / "Pillars.json"
    source_card = save_scene(create_scene("Source", now=NOW), source, now=NOW)
    destination = users / "Pillars.json"
    users.mkdir()
    destination.write_text(json.dumps(document(create_scene("User", now=NOW))), encoding="utf-8")
    asset = users / "Pillars" / "reprojected.fits"
    asset.parent.mkdir()
    asset.write_bytes(b"retained reprojection")
    before_user = destination.read_bytes()

    with pytest.raises(FileExistsError, match="already exists"):
        materialize_example(source, users)
    assert destination.read_bytes() == before_user
    assert asset.read_bytes() == b"retained reprojection"

    copied, copied_path = materialize_example(source, users, overwrite=True)
    assert copied_path == destination.resolve()
    assert copied.scene_id == source_card.scene_id
    assert destination.read_bytes() == source.read_bytes()
    assert asset.read_bytes() == b"retained reprojection"


def test_example_open_prefers_existing_user_copy(tmp_path: Path) -> None:
    examples = tmp_path / "examples"
    users = tmp_path / "users"
    examples.mkdir()
    source = examples / "Pillars.json"
    original = save_scene(create_scene("Example", now=NOW), source, now=NOW)
    copied, destination = materialize_example(source, users)
    user = edit_scene(copied, {"title": "User-edited title"})
    save_scene(user, destination, now="2026-09-14T12:01:00Z")

    opened, opened_path = open_example_user_copy(source, users)
    assert opened_path == example_user_path(source, users)
    assert opened.title == "User-edited title"
    assert opened.scene_id == original.scene_id


def test_example_entry_uses_thumbnail_from_user_copy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    examples = project / "examples"
    users = tmp_path / "users"
    examples.mkdir(parents=True)
    source = examples / "Pillars.json"
    save_scene(create_scene("Pillars", now=NOW), source, now=NOW)
    copied, destination = materialize_example(source, users)
    thumbnail = users / "Pillars" / "thumbnail.png"
    thumbnail.parent.mkdir()
    Image.new("RGB", (4, 3), (1, 2, 3)).save(thumbnail)
    data = document(copied)
    data["assets"] = {"thumb": {
        "kind": "discovery_thumbnail", "path": "Pillars/thumbnail.png",
        "source_url": "https://example.test/pillars",
    }}
    data["thumbnail_asset_id"] = "thumb"
    save_scene(SceneCard.model_validate(data), destination, now="2026-09-14T12:01:00Z")

    library = list_project_library(users, project)
    assert library.examples[0].thumbnail_path == thumbnail.resolve()
    assert library.examples[0].thumbnail_kind == "external discovery image"


def test_save_uses_scene_directory_and_duplicate_has_new_identity(tmp_path: Path) -> None:
    card = create_scene("Cool Scene", now=NOW)
    saved, path = save_draft(card, tmp_path)
    assert path == default_scene_path(card, tmp_path)
    entry = next(item for item in list_scene_library(tmp_path) if item.card)
    copied, copied_path = duplicate_library_scene(entry, tmp_path)
    assert copied.scene_id != saved.scene_id
    assert copied_path != path
    assert copied.title == "Cool Scene copy"
    assert copied_path.is_file()
    assert load_scene(copied_path) == copied
    assert copied.renders is None


def test_library_duplicate_materializes_source_assets(tmp_path: Path) -> None:
    card = create_scene("Pillars", now=NOW)
    data = document(card)
    data["assets"] = {
        "source": {"kind": "source", "path": "Pillars/inputs/source.fits"},
    }
    source_path = tmp_path / "Pillars.json"
    saved = save_scene(
        SceneCard.model_validate(data), source_path,
        asset_contents={"source": b"fits-source"}, now=NOW,
    )
    entry = next(item for item in list_scene_library(tmp_path) if item.card)

    copied, copied_path = duplicate_library_scene(entry, tmp_path)
    copied_asset = copied.assets["source"]
    copied_binary = copied_path.parent / copied_asset.path

    assert copied_path.is_file()
    assert copied.scene_id != saved.scene_id
    assert copied_binary.is_file()
    assert copied_binary.read_bytes() == b"fits-source"
    copied_binary.unlink()
    assert (tmp_path / "Pillars/inputs/source.fits").read_bytes() == b"fits-source"


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


def test_resolver_match_draft_does_not_repeat_typed_query_as_resolved_name() -> None:
    card = draft_from_resolver_match(
        "horsehead nebula",
        ResolverMatch("horsehead nebula", 85.24583333, -2.45833333),
        "astropy-name-resolver",
        region_size_arcmin=3.0,
    )

    assert card.title == "horsehead nebula"
    assert card.target.name == "horsehead nebula"
    assert card.target.resolved_name is None
    assert card.discovery.sources[0].extracted_metadata["resolved_label"] == "horsehead nebula"


def test_export_requires_current_render_and_explicit_overwrite(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    output = tmp_path / "exports" / "image"
    exported = export_current_render(card, path, output, output_format="png", branch="original")
    final = output.with_suffix(".png")
    with Image.open(final) as image:
        assert image.format == "PNG"
    assert exported.exports[-1].destination == str(final.resolve())
    with pytest.raises(FileExistsError):
        export_current_render(exported, path, final, output_format="png", branch="original")
    assert len(load_scene(path).exports) == 1


def test_tiff_export_contains_tiff_data(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    output = tmp_path / "exports" / "image.tiff"
    export_current_render(card, path, output, output_format="tiff", branch="original")
    exported = imread(output)
    assert exported.dtype == np.uint16
    assert np.unique(exported).size > 256


def test_export_rejects_stale_or_unrendered_scene(tmp_path: Path) -> None:
    card = ready_card()
    path = tmp_path / "draft.json"
    save_scene(card, path)
    with pytest.raises(ValueError, match="current successful render"):
        export_current_render(card, path, tmp_path / "out.png", output_format="png", branch="original")


def test_tiff_export_rejects_render_without_high_depth_role(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    data = document(card)
    high_depth_id = data["renders"][-1].pop("high_depth_image_asset_id")
    data["assets"].pop(high_depth_id)
    legacy = SceneCard.model_validate(data)

    with pytest.raises(ValueError, match="does not register a tiff output artifact"):
        export_current_render(
            legacy,
            path,
            tmp_path / "out.tiff",
            output_format="tiff",
            branch="original",
        )


def test_tiff_export_copies_explicit_deconvolved_branch_role(tmp_path: Path) -> None:
    card, path = rendered_card(tmp_path)
    kernel = tmp_path / "assets" / "kernel.fits"
    fits.PrimaryHDU(data=np.ones((3, 3), dtype=np.float32)).writeto(kernel)
    data = document(card)
    data["content_revision"] += 1
    data["assets"]["kernel"] = {"kind": "psf_kernel", "path": "assets/kernel.fits"}
    data["psf"] = {
        "enabled": True,
        "per_plane": {
            "mast:a": {
                "enabled": True, "kernel_asset_id": "kernel",
                "max_iterations": 4, "regularization": 0.0,
            },
            "mast:b": {"enabled": False},
        },
    }
    processed = SceneCard.model_validate(data)
    preview = tmp_path / "assets" / "deconvolved.png"
    high_depth = tmp_path / "assets" / "deconvolved.tiff"
    provenance = tmp_path / "assets" / "deconvolved-provenance.json"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(preview)
    expected = np.full((4, 4, 3), 54321, dtype=np.uint16)
    imwrite(high_depth, expected, photometric="rgb")
    provenance.write_text("{}", encoding="utf-8")
    processed = append_render(
        processed,
        snapshot=processed,
        branch="deconvolved",
        plane_filters={"mast:a": "F090W", "mast:b": "F444W"},
        image_asset_id="deconvolved-preview",
        high_depth_image_asset_id="deconvolved-high-depth",
        provenance_asset_id="deconvolved-provenance",
        assets={
            "deconvolved-preview": Asset(kind="render_image", path="assets/deconvolved.png"),
            "deconvolved-high-depth": Asset(kind="render_image", path="assets/deconvolved.tiff"),
            "deconvolved-provenance": Asset(
                kind="provenance", path="assets/deconvolved-provenance.json"
            ),
        },
        now=NOW,
    )
    processed = save_scene(processed, path, expected_previous=card)
    destination = tmp_path / "exports" / "deconvolved.tiff"

    export_current_render(
        processed,
        path,
        destination,
        output_format="tiff",
        branch="deconvolved",
    )

    assert np.array_equal(imread(destination), expected)

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs.utils import proj_plane_pixel_scales
import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from galaxy import pipeline
from galaxy.bridge import prepare_native_presentation
from galaxy.checkpoints import (
    CheckpointValidationError, build_producer_inputs, checkpoint_manifest_path,
    load_validated_checkpoint, producer_dependency_key, write_checkpoint_manifest,
)
from galaxy.fitsio import load_fits_plane
from galaxy.mapping import CompositionInputs, compose_channels_with_diagnostics, compute_derived_planes
from galaxy.planes import export_multiplane_fits, load_multiplane_records
from galaxy.processing_config import DerivedPlaneConfig, MappingConfig
from galaxy.reprojection import ReprojectedPlane, reproject_plane
from galaxy.scene_card import create_scene, document, edit_scene, load_scene, save_scene
from galaxy.scene_execution import prepare_scene_execution
from galaxy.scene_models import SceneCard
from galaxy.scene_pipeline import run_scene_pipeline
from galaxy.scene_readiness import readiness
from galaxy.scene_workflow import Screen, duplicate_library_scene, list_scene_library, matching_render


FIXTURE = Path(__file__).parent / "fixtures/reprojection_bridge/pillars_f090w_core.fits"


def _card(directory: Path, *, enabled: bool | None = True, adaptive: bool = False) -> tuple[Path, SceneCard]:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "source.fits"
    shutil.copyfile(FIXTURE, source)
    plane = load_fits_plane(source)
    ra, dec = plane.wcs.pixel_to_world_values(33.5, 33)
    scale = float(np.mean(proj_plane_pixel_scales(plane.wcs))) * 3600
    changes = {
        "selection": {"products": [{"product_id": "fixture-product", "archive": "MAST",
            "filename": "source.fits", "filter": "F090W", "cached_asset_id": "source"}],
            "selected_product_ids": ["fixture-product"]},
        "canvas": {"center": {"mode": "explicit", "ra_deg": float(ra), "dec_deg": float(dec)},
            "projection": "TAN", "pixel_scale_arcsec": scale, "width": 68, "height": 67,
            "rotation_deg": 0., "flux_conserving": adaptive},
        "planes": {"enabled_filters": ["F090W"], "disabled_plane_ids": [], "export_multiplane_fits": True},
        "mapping": {"planes": [{"filter": "F090W", "rgb": {"red": 1., "green": 1., "blue": 1.}}],
            "defaults": {"normalization": {"mode": "percentile", "black_percentile": 0., "white_percentile": 100.}}},
        "tone": {"stretch": {c: {"kind": "gamma", "parameter": 1.} for c in ("red", "green", "blue")},
            "percentiles": {"black": 0., "white": 100.}, "saturation": 1.,
            "gain": {c: 1. for c in ("red", "green", "blue")},
            "bias": {c: 0. for c in ("red", "green", "blue")}},
        "psf": {"enabled": False},
        "assets": {"source": {"kind": "source", "path": "source.fits"}},
    }
    if enabled is not None:
        changes["bridge"] = {"enabled": enabled}
    card = SceneCard.model_validate({**document(create_scene("Bridge specimen")), **changes})
    path = directory / "scene.json"
    return path, save_scene(card, path)


@pytest.mark.parametrize("adaptive", [False, True])
def test_real_pipeline_on_off_support_history_and_compose_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, adaptive: bool,
) -> None:
    path, card = _card(tmp_path, adaptive=adaptive)
    source = tmp_path / "source.fits"
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    on = run_scene_pipeline(path)
    aligned = load_multiplane_records(on.artifacts.planes_path, require_bridge_support=True)[0]
    assert aligned.metadata["bridge"]["estimated_samples"] == 6
    assert aligned.estimate_influence.any()
    assert np.any(aligned.presentation_valid & ~aligned.valid)
    assert matching_render(on.card) is not None
    assert on.card.renders[-1].inputs.bridge.enabled is True
    assert on.artifacts.png_path.is_file() and on.artifacts.tiff_path.is_file()
    manifest = json.loads(on.artifacts.provenance_path.read_text())
    assert manifest["bridge"]["enabled"] is True
    assert manifest["planes"][0]["bridge"]["estimated_samples"] == 6
    # Strict compose-only reuses the certified stack without native preparation.
    launch = prepare_scene_execution(on.card, path)
    def no_preparation(*args: object, **kwargs: object) -> None:
        raise AssertionError("compose-only must not bridge native inputs")
    monkeypatch.setattr(pipeline, "prepare_native_presentation", no_preparation)
    reused = pipeline._load_or_build_reprojected(
        launch.config, SkyCoord(launch.config.canvas.center.ra_deg, launch.config.canvas.center.dec_deg, unit="deg"),
        [source], on.artifacts.workdir / "cache", on.artifacts.workdir, on.artifacts.workdir,
        "compose-only", None, source_ids_by_path={source.resolve(): "fixture-product"},
    )
    np.testing.assert_array_equal(reused.original_planes[0].estimate_influence, aligned.estimate_influence)
    off_card = edit_scene(on.card, {"bridge": {"enabled": False}})
    assert matching_render(off_card) is None
    off_launch = prepare_scene_execution(off_card, path)
    with pytest.raises(CheckpointValidationError, match="dependency mismatch"):
        pipeline._load_or_build_reprojected(
            off_launch.config, SkyCoord(off_launch.config.canvas.center.ra_deg, off_launch.config.canvas.center.dec_deg, unit="deg"),
            [source], on.artifacts.workdir / "cache", on.artifacts.workdir, on.artifacts.workdir,
            "compose-only", None, source_ids_by_path={source.resolve(): "fixture-product"},
        )
    monkeypatch.undo()
    save_scene(off_card, path)
    off = run_scene_pipeline(path)
    strict = load_multiplane_records(off.artifacts.planes_path)[0]
    assert not strict.estimate_influence.any()
    np.testing.assert_array_equal(strict.footprint, aligned.footprint)
    np.testing.assert_array_equal(strict.valid, aligned.valid)
    assert off.card.renders[-1].inputs.bridge.enabled is False
    assert off.card.renders[-2].inputs.bridge.enabled is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest


@pytest.mark.parametrize("adaptive", [False, True])
def test_actual_kernel_influence_is_broader_than_native_mask(adaptive: bool) -> None:
    plane = load_fits_plane(FIXTURE)
    presentation = prepare_native_presentation(plane)
    wcs = plane.wcs.deepcopy()
    wcs.wcs.crpix += .5
    aligned = reproject_plane(plane, wcs, plane.data.shape, adaptive, presentation=presentation)
    strict = reproject_plane(plane, wcs, plane.data.shape, adaptive)
    assert np.count_nonzero(aligned.estimate_influence) > 6
    assert not np.any(aligned.statistics_valid & aligned.estimate_influence)
    np.testing.assert_array_equal(aligned.valid, strict.valid)
    np.testing.assert_array_equal(aligned.footprint, strict.footprint)


@pytest.mark.parametrize("long_identifier", [False, True])
def test_stack_and_single_plane_preserve_masks_and_missing_extension_is_rejected(
    tmp_path: Path, long_identifier: bool,
) -> None:
    from galaxy.reprojection import save_reprojected_plane
    plane = load_fits_plane(FIXTURE)
    aligned = reproject_plane(plane, plane.wcs, plane.data.shape, False, presentation=prepare_native_presentation(plane))
    if long_identifier:
        aligned.plane_id = "archive-product-" + "x" * 100
    path = export_multiplane_fits([aligned], tmp_path / "stack.fits")
    restored = load_multiplane_records(path, require_bridge_support=True)[0]
    assert restored.plane_id == aligned.plane_id
    for name in ("data", "valid", "footprint", "presentation_support", "estimate_influence"):
        np.testing.assert_array_equal(getattr(restored, name), getattr(aligned, name))
    single, _ = save_reprojected_plane(aligned, plane.wcs, tmp_path / "single")
    with fits.open(single) as hdul:
        assert {h.header.get("GALTYPE") for h in hdul[1:]} == {"OBS_SUPPORT", "PRESENT_SUPPORT", "ESTIMATE_INFLUENCE"}
        assert hdul[0].header["SUPVER"] == 1
    with fits.open(path) as hdul:
        copied = [h.copy() for h in hdul if h.header.get("GALTYPE") != "ESTIMATE_INFLUENCE"]
    fits.HDUList(copied).writeto(tmp_path / "missing.fits")
    with pytest.raises(ValueError, match="missing certified bridge support"):
        load_multiplane_records(tmp_path / "missing.fits", require_bridge_support=True)


def test_bridge_state_version_and_old_checkpoint_invalidate_identity(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    launch = prepare_scene_execution(card, path)
    inputs = build_producer_inputs(launch.config, [tmp_path / "source.fits"], "original", resolved_center_deg=(0, 0))
    altered = deepcopy(inputs)
    altered["bridge"]["algorithm_version"] = "next-version"
    assert producer_dependency_key(inputs) != producer_dependency_key(altered)
    result = run_scene_pipeline(path)
    manifest_path = result.artifacts.checkpoint_manifest_path
    doc = json.loads(manifest_path.read_text())
    doc["format_version"] = 1
    manifest_path.write_text(json.dumps(doc))
    with pytest.raises(CheckpointValidationError, match="invalid checkpoint manifest"):
        load_validated_checkpoint(result.artifacts.planes_path, manifest_path, inputs, "original")


def _estimated_plane() -> ReprojectedPlane:
    values = np.array([[1, 2, 3], [4, 1000, 5]], dtype=np.float32)
    observed = np.ones(values.shape, dtype=bool)
    observed[1, 1] = False
    influence = ~observed
    return ReprojectedPlane("p", values, observed.astype(np.float32), {"native_unit": "MJy/sr"},
        wcs=load_fits_plane(FIXTURE).wcs, valid=observed,
        presentation_support=np.ones(values.shape, dtype=np.float32), estimate_influence=influence)


def test_estimates_display_but_do_not_set_normalization_or_tone_statistics() -> None:
    from galaxy.coverage import apply_coverage_policy
    from galaxy.processing_config import CoverageConfig
    plane = _estimated_plane()
    mapping = MappingConfig.model_validate({"planes": [{"plane": "p", "rgb": {"red": 1}}],
        "defaults": {"normalization": {"mode": "percentile", "black_percentile": 0, "white_percentile": 100}}})
    composition = compose_channels_with_diagnostics(CompositionInputs({"p": plane}), mapping)
    assert composition.plane_diagnostics["p"]["white_point"] == 5
    assert composition.channels["red"][1, 1] == 1
    application = apply_coverage_policy(composition, CoverageConfig())
    assert application.output_masks["red"][1, 1]
    assert not application.tone_masks["red"][1, 1]


def test_derived_ratios_and_zero_weight_contributors_preserve_support_identity() -> None:
    plane = _estimated_plane()
    denominator = ReprojectedPlane("den", np.full(plane.data.shape, 2, dtype=np.float32),
        np.ones(plane.data.shape), {}, wcs=plane.wcs)
    zero = ReprojectedPlane("zero", np.zeros(plane.data.shape), np.zeros(plane.data.shape), {}, wcs=plane.wcs)
    definition = DerivedPlaneConfig.model_validate({"name": "ratio", "operation": "ratio",
        "numerator": [{"plane": "p", "weight": 1}, {"plane": "zero", "weight": 0}],
        "denominator": [{"plane": "den", "weight": 1}]})
    # Ratio units must be compatible.
    denominator.metadata["native_unit"] = "MJy/sr"
    result = compute_derived_planes({"p": plane, "den": denominator, "zero": zero}, [definition])["ratio"]
    assert result.data[1, 1] == 500
    assert result.presentation_valid[1, 1] and result.estimate_influence[1, 1]
    assert not result.valid[1, 1]
    assert "zero" not in result.parent_ids


def test_preparation_failure_aborts_even_when_fits_load_is_not_fail_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, card = _card(tmp_path)
    save_scene(edit_scene(card, {"execution": {"fail_fast": False}}), path)
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("source: injected bridge failure")
    monkeypatch.setattr(pipeline, "prepare_native_presentation", fail)
    with pytest.raises(RuntimeError, match="injected bridge failure"):
        run_scene_pipeline(path)
    assert not load_scene(path).renders


def test_old_scene_defaults_on_and_old_history_is_stale(tmp_path: Path) -> None:
    path, card = _card(tmp_path, enabled=None)
    assert card.bridge is None
    assert prepare_scene_execution(card, path).config.bridge.enabled is True
    result = run_scene_pipeline(path)
    data = document(result.card)
    data["renders"][-1]["inputs"].pop("bridge")
    old = SceneCard.model_validate(data)
    assert matching_render(old) is None
    assert any(item.code == "stale" for item in readiness(old, "export"))


def test_explicit_off_survives_save_reopen_duplicate_and_strict_boolean_validation(tmp_path: Path) -> None:
    path, card = _card(tmp_path, enabled=False)
    assert load_scene(path).bridge.enabled is False
    entry = next(entry for entry in list_scene_library(tmp_path) if entry.path == path.resolve())
    duplicate, _ = duplicate_library_scene(entry, tmp_path)
    assert duplicate.bridge.enabled is False
    data = document(card)
    data["bridge"]["enabled"] = "false"
    with pytest.raises(ValueError):
        SceneCard.model_validate(data)


def test_streamlit_switch_defaults_changes_and_locks() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from galaxy.scene_card import create_scene\n"
        "from galaxy.ui import _render_bridge\n"
        "st.session_state.setdefault('active_card', create_scene('Bridge'))\n"
        "_render_bridge(st.session_state['active_card'])\n"
    ).run()
    assert not app.exception
    assert app.toggle[0].label == "Bridge small NaN holes" and app.toggle[0].value is True
    app.toggle[0].set_value(False).run()
    assert app.session_state["active_card"].bridge.enabled is False
    from galaxy.scene_workflow import OperationPhase
    app.session_state["render_job"] = SimpleNamespace(snapshot=lambda: SimpleNamespace(phase=OperationPhase.RUNNING))
    app.run()
    assert app.toggle[0].disabled


@pytest.mark.parametrize("adaptive", [False, True])
def test_psf_branch_receives_observations_and_prepares_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, adaptive: bool,
) -> None:
    path, card = _card(tmp_path, adaptive=adaptive)
    source = tmp_path / "source.fits"
    # Synthetic positive pedestal gives the existing nonnegative RL its valid
    # domain. Missing core, WHT and surrounding shape remain represented.
    with fits.open(source) as hdul:
        hdus = [h.copy() for h in hdul]
    hdus[1].data = hdus[1].data + 100
    fits.HDUList(hdus).writeto(source, overwrite=True)
    kernel = tmp_path / "kernel.fits"
    fits.PrimaryHDU(np.ones((1, 1), dtype=np.float32)).writeto(kernel)
    data = document(card)
    data["assets"]["kernel"] = {"kind": "psf_kernel", "path": "kernel.fits"}
    psf = {"enabled": True, "per_plane": {"source": {
        "enabled": True, "kernel_asset_id": "kernel", "max_iterations": 1, "regularization": 0}}}
    save_scene(edit_scene(SceneCard.model_validate(data), {"psf": psf}), path)
    actual_builder = pipeline.build_deconvolved_plane_artifacts
    observed_inputs = []
    def checked_builder(planes: list, *args: object, **kwargs: object) -> list:
        assert np.isnan(planes[0].data[32:34, 32:35]).all()
        assert not planes[0].valid[32:34, 32:35].any()
        observed_inputs.append(planes[0].data.copy())
        return actual_builder(planes, *args, **kwargs)
    monkeypatch.setattr(pipeline, "build_deconvolved_plane_artifacts", checked_builder)
    result = run_scene_pipeline(path)
    assert len(observed_inputs) == 1
    assert result.artifacts.deconvolved_png_path.is_file()
    for asset in (result.artifacts.planes_path, result.artifacts.deconvolved_planes_path):
        plane = load_multiplane_records(asset, require_bridge_support=True)[0]
        assert plane.metadata["bridge"]["estimated_samples"] == 6
        assert plane.estimate_influence.any()
    assert {r.branch for r in result.card.renders} == {"original", "deconvolved"}


def test_streamlit_save_generate_preview_and_stale_export_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, _ = _card(tmp_path, enabled=None)
    monkeypatch.setenv("GALAXY_UI_INPUT_PATH", str(path))
    app = AppTest.from_string(
        "import sys, os\n"
        f"sys.argv = ['ui.py', '--scene-dir', {str(tmp_path)!r}]\n"
        "from galaxy.ui import main\nmain()\n", default_timeout=20,
    ).run(timeout=20)
    app = app.sidebar.radio[0].set_value(Screen.REFINEMENT.value).run(timeout=20)
    assert not app.exception
    toggle = next(t for t in app.toggle if t.label == "Bridge small NaN holes")
    assert toggle.value is True
    app = toggle.set_value(False).run(timeout=20)
    app = app.button(key="refinement-save").click().run(timeout=20)
    assert load_scene(path).bridge.enabled is False
    app = app.sidebar.radio[0].set_value(Screen.RENDER.value).run(timeout=20)
    app = next(b for b in app.button if b.label == "Generate preview").click().run(timeout=20)
    job = app.session_state["render_job"]
    assert job.wait(20), "real crop render must reach a terminal state"
    app.run(timeout=20)
    assert not app.exception
    saved = load_scene(path)
    assert not any("No preview has been generated" in item.value for item in app.info)
    assert saved.renders[-1].inputs.bridge.enabled is False
    assert matching_render(saved) is not None
    app = app.sidebar.radio[0].set_value(Screen.REFINEMENT.value).run(timeout=20)
    app = next(t for t in app.toggle if t.label == "Bridge small NaN holes").set_value(True).run(timeout=20)
    assert matching_render(app.session_state["active_card"]) is None
    assert any("requires reprojection" in str(t.help) for t in app.toggle)


@pytest.mark.parametrize("telescope", ["HST", "JWST"])
@pytest.mark.parametrize("adaptive", [False, True])
def test_no_hole_source_pipeline_on_off_is_exact(
    tmp_path: Path, telescope: str, adaptive: bool,
) -> None:
    path, card = _card(tmp_path, adaptive=adaptive)
    source = tmp_path / "source.fits"
    with fits.open(source, mode="update") as hdul:
        invalid = ~np.isfinite(hdul["SCI"].data)
        hdul["SCI"].data[invalid] = 489.006088
        hdul["WHT"].data[invalid] = 1
        hdul["CON"].data[..., invalid] = 1
        hdul[0].header["TELESCOP"] = telescope
    on = run_scene_pipeline(path)
    prepared = load_multiplane_records(on.artifacts.planes_path, require_bridge_support=True)[0]
    assert prepared.metadata["bridge"]["estimated_samples"] == 0
    assert not prepared.estimate_influence.any()
    save_scene(edit_scene(on.card, {"bridge": {"enabled": False}}), path)
    off = run_scene_pipeline(path)
    strict = load_multiplane_records(off.artifacts.planes_path, require_bridge_support=True)[0]
    for field in ("data", "valid", "footprint", "presentation_support", "estimate_influence"):
        np.testing.assert_array_equal(getattr(prepared, field), getattr(strict, field))
    assert on.artifacts.png_path.read_bytes() == off.artifacts.png_path.read_bytes()

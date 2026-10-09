from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from galaxy import cli
from galaxy.background import estimate_background
import galaxy.scene_pipeline as scene_pipeline_module
from galaxy.scene_card import document, edit_scene, load_scene, save_scene
from galaxy.scene_execution import SceneNotReadyError, prepare_scene_execution
from galaxy.scene_models import SceneCard
from galaxy.scene_pipeline import run_scene_pipeline
from galaxy.pipeline import PipelineCancelled
from galaxy.planes import load_multiplane_records
from galaxy.processing_config import (
    BackgroundConfig, BackgroundEstimatorConfig, SkyRectangleConfig,
)
from galaxy.render_jobs import request_cancellation_before_departure, start_render_job
from galaxy.mast import download_selected
from galaxy.selection import CandidateManifest, CandidateRecord, SelectionInputs, write_candidate_manifest


NOW = "2026-09-14T12:00:00Z"


def _write_source(path: Path) -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [2.0, 2.0]
    wcs.wcs.cdelt = [-0.00002777778, 0.00002777778]
    header = wcs.to_header()
    header["FILTER"] = "F200W"
    header["INSTRUME"] = "NIRCAM"
    header["TELESCOP"] = "JWST"
    header["OBS_ID"] = "OBS1"
    fits.PrimaryHDU(data=np.arange(16, dtype=np.float32).reshape(4, 4), header=header).writeto(path)


def _card(tmp_path: Path) -> tuple[Path, SceneCard]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.fits"
    _write_source(source)
    payload = {
        "document_type": "galaxy.scene_card", "schema_version": 1,
        "scene_id": "12345678-1234-4234-8234-123456789abc", "title": "Pinned",
        "created_at": NOW, "updated_at": NOW, "content_revision": 1,
        "selection": {
            "products": [{"product_id": "mast:exact-v1", "archive": "MAST", "filename": "source.fits",
                          "observation_id": "OBS1", "mission": "JWST", "instrument": "NIRCAM",
                          "filter": "F200W", "product_type": "SCIENCE", "cached_asset_id": "source"}],
            "selected_product_ids": ["mast:exact-v1"],
        },
        "canvas": {"center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
                   "projection": "TAN", "pixel_scale_arcsec": 0.1, "width": 4, "height": 4,
                   "rotation_deg": 0.0, "flux_conserving": False},
        "planes": {"enabled_filters": ["F200W"], "disabled_plane_ids": [],
                   "export_multiplane_fits": True},
        "mapping": {"planes": [{"plane": "source", "rgb": {"red": 1.0, "green": 0.5, "blue": 0.25}}]},
        "tone": {
            "stretch": {channel: {"kind": "asinh", "parameter": 4.0}
                        for channel in ("red", "green", "blue")},
            "percentiles": {"black": 0.0, "white": 100.0},
            "gain": {channel: 1.0 for channel in ("red", "green", "blue")},
            "bias": {channel: 0.0 for channel in ("red", "green", "blue")},
            "saturation": 1.0,
        },
        "psf": {"enabled": False},
        "execution": {"fail_fast": True, "log_file": "galaxy.log",
                      "debug_to_console": False, "debug_to_file": True},
        "assets": {"source": {"kind": "source", "path": "source.fits"}},
    }
    path = tmp_path / "pinned.scene.json"
    card = save_scene(SceneCard.model_validate(payload), path, now=NOW)
    return path, card


def test_prepare_scene_execution_preserves_exact_pins_and_has_no_yaml(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    launch = prepare_scene_execution(card, path)
    assert [candidate.candidate_id for candidate in launch.selection_manifest.candidates] == ["mast:exact-v1"]
    assert all(candidate.selected for candidate in launch.selection_manifest.candidates)
    assert launch.local_product_paths["mast:exact-v1"] == tmp_path / "source.fits"
    assert launch.config.canvas.center.mode == "explicit"
    assert launch.config.mapping.planes[0].plane == "source"


def test_prepare_scene_execution_keeps_resolved_name_out_of_processing_target(
    tmp_path: Path,
) -> None:
    path, card = _card(tmp_path)
    card = edit_scene(card, {"target": {
        "name": "horsehead nebula",
        "resolved_name": "Horsehead Nebula",
        "ra_deg": 85.24583333,
        "dec_deg": -2.45833333,
        "coordinate_frame": "ICRS",
        "region": {"kind": "box", "width_arcmin": 2.0, "height_arcmin": 2.0},
    }})

    launch = prepare_scene_execution(card, path)

    assert launch.card.target.resolved_name == "Horsehead Nebula"
    assert launch.config.target.name == "horsehead nebula"
    assert "resolved_name" not in launch.config.target.model_dump()
    assert "coordinate_frame" not in launch.config.target.model_dump()


def test_scene_pipeline_uses_local_pin_records_history_and_writes_no_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, card = _card(tmp_path)
    monkeypatch.setattr("galaxy.pipeline.discover_candidates",
                        lambda *args, **kwargs: pytest.fail("pinned run must not discover"))
    monkeypatch.setattr("galaxy.pipeline.download_selected",
                        lambda *args, **kwargs: pytest.fail("local pin must not download"))

    result = run_scene_pipeline(path)
    reopened = load_scene(path)
    assert result.card == reopened
    assert reopened.scene_id == card.scene_id
    assert len(reopened.renders) == 1
    record = reopened.renders[0]
    assert record.branch == "original"
    assert record.content_revision == card.content_revision
    assert record.inputs.selection.selected_product_ids == ["mast:exact-v1"]
    assert reopened.assets[record.image_asset_id].kind == "render_image"
    assert reopened.assets[record.image_asset_id].sha256 is not None
    assert record.high_depth_image_asset_id is not None
    assert reopened.assets[record.high_depth_image_asset_id].kind == "render_image"
    assert record.checkpoint_manifest_asset_id is not None
    checkpoint_asset = reopened.assets[record.checkpoint_manifest_asset_id]
    assert checkpoint_asset.kind == "checkpoint_manifest"
    assert (path.parent / checkpoint_asset.path).is_file()
    assert result.artifacts.planes_path == result.artifacts.workdir / "original" / "aligned-planes.fits"
    assert result.artifacts.checkpoint_manifest_path == result.artifacts.workdir / "original" / "aligned-checkpoint.json"
    assert result.artifacts.png_path == result.artifacts.workdir / "original" / "composite.png"
    assert result.artifacts.tiff_path == result.artifacts.workdir / "original" / "composite.tiff"
    assert (result.artifacts.workdir / "original" / "aligned").is_dir()
    assert reopened.assets[record.provenance_asset_id].kind == "provenance"
    assert record.thumbnail_asset_id == reopened.thumbnail_asset_id
    thumbnail = reopened.assets[record.thumbnail_asset_id]
    assert thumbnail.kind == "render_thumbnail"
    assert (path.parent / thumbnail.path).is_file()
    assert result.artifacts.config_path == path
    assert not list(tmp_path.rglob("*.yaml"))
    candidates = json.loads((result.artifacts.workdir / "candidates.json").read_text())
    assert [item["candidate_id"] for item in candidates["candidates"] if item["selected"]] == ["mast:exact-v1"]
    provenance = json.loads(result.artifacts.provenance_path.read_text())
    assert provenance["selection"]["source"] == "pinned_scene_card"
    assert provenance["stage_records"][0]["stage_id"] == "aligned_checkpoint"
    assert provenance["stage_records"][0]["branch"] == "original"
    assert provenance["stage_records"][0]["output_content_identity"]["sha256"]


def test_first_render_replaces_provisional_search_frame_and_persists_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, card = _card(tmp_path)
    canvas = document(card.canvas)
    canvas["width"] = 1
    canvas["height"] = 1
    canvas["frame_origin"] = "search_region"
    provisional = edit_scene(card, {"canvas": canvas})
    save_scene(provisional, path, expected_previous=card, now=NOW)
    monkeypatch.setattr("galaxy.pipeline.discover_candidates",
                        lambda *args, **kwargs: pytest.fail("pinned run must not discover"))
    monkeypatch.setattr("galaxy.pipeline.download_selected",
                        lambda *args, **kwargs: pytest.fail("local pin must not download"))

    result = run_scene_pipeline(path)
    reopened = load_scene(path)

    assert reopened == result.card
    assert reopened.canvas.frame_origin == "selected_footprints"
    assert reopened.canvas.width > 1 and reopened.canvas.height > 1
    assert reopened.content_revision == provisional.content_revision + 1
    assert reopened.renders[0].inputs.canvas.frame_origin == "selected_footprints"
    assert result.artifacts.effective_canvas == document(reopened.canvas)


def test_applied_background_survives_reopen_and_registers_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, _ = _card(tmp_path)
    monkeypatch.setattr("galaxy.pipeline.discover_candidates",
                        lambda *args, **kwargs: pytest.fail("pinned run must not discover"))
    monkeypatch.setattr("galaxy.pipeline.download_selected",
                        lambda *args, **kwargs: pytest.fail("local pin must not download"))
    baseline = run_scene_pipeline(path)
    planes = load_multiplane_records(baseline.artifacts.planes_path)
    ra, dec = planes[0].wcs.pixel_to_world_values(1.5, 1.5)
    background = BackgroundConfig(
        mode="pedestal",
        black_reference_policy="corrected_zero",
        inclusion_regions=[SkyRectangleConfig(
            region_id="sky", center_ra_deg=float(ra), center_dec_deg=float(dec),
            width_arcsec=0.35, height_arcsec=0.35,
        )],
        estimator=BackgroundEstimatorConfig(
            minimum_samples=4, minimum_valid_fraction=0.25,
        ),
    )
    proposal = estimate_background(planes, background)
    applied = edit_scene(baseline.card, {"background": {
        **background.model_dump(mode="json"),
        "resolved_branches": {
            "original": {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in proposal.resolved_planes.items()
            }
        },
    }})
    saved = save_scene(applied, path, expected_previous=baseline.card)
    assert load_scene(path).background.mode == "pedestal"

    corrected = run_scene_pipeline(path)
    reopened = load_scene(path)
    record = reopened.renders[-1]
    assert corrected.card == reopened
    assert record.content_revision == saved.content_revision
    assert record.background_diagnostic_asset_ids is not None
    assert {reopened.assets[asset_id].kind for asset_id in record.background_diagnostic_asset_ids} == {
        "background_diagnostic", "background_region_overlay",
    }
    for asset_id in record.background_diagnostic_asset_ids:
        assert (path.parent / reopened.assets[asset_id].path).is_file()
    provenance = json.loads(corrected.artifacts.provenance_path.read_text())
    stage = next(item for item in provenance["stage_records"]
                 if item["stage_id"] == "background_pedestal")
    assert stage["branch"] == "original"


def test_scene_pipeline_rejects_mapping_after_actual_plane_inspection(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    mapping = document(card)["mapping"]
    mapping["planes"][0]["plane"] = "invented-from-filename"
    save_scene(edit_scene(card, {"mapping": mapping}), path, now=NOW)
    with pytest.raises(ValueError, match="unknown plane"):
        run_scene_pipeline(path)
    assert load_scene(path).renders is None


def test_scene_workdir_must_be_associated_with_card(tmp_path: Path) -> None:
    path, _ = _card(tmp_path / "scene")
    with pytest.raises(ValueError, match="inside"):
        run_scene_pipeline(path, tmp_path / "outside")


def test_scene_workdir_cannot_overwrite_registered_render_assets(tmp_path: Path) -> None:
    path, _ = _card(tmp_path)
    first = run_scene_pipeline(path)
    before = first.artifacts.png_path.read_bytes()
    with pytest.raises(ValueError, match="immutable registered asset"):
        run_scene_pipeline(path, first.artifacts.workdir)
    assert first.artifacts.png_path.read_bytes() == before


def test_canvas_change_can_replace_unreferenced_reprojections(tmp_path: Path) -> None:
    path, original = _card(tmp_path)
    workdir = tmp_path / "Pillars" / "retained-render"
    first = run_scene_pipeline(path, workdir)
    source_before = (tmp_path / "source.fits").read_bytes()
    first.artifacts.png_path.write_bytes(b"obsolete preview")

    canvas = document(original.canvas)
    canvas["rotation_deg"] = 5.0
    changed = edit_scene(original, {"canvas": canvas})
    # Example JSON replacement may intentionally leave the old asset folder in place.
    path.write_text(json.dumps(document(changed)), encoding="utf-8")

    second = run_scene_pipeline(path, workdir)
    assert second.artifacts.png_path.read_bytes() != b"obsolete preview"
    assert (tmp_path / "source.fits").read_bytes() == source_before
    assert load_scene(path).canvas.rotation_deg == 5.0


def test_missing_local_pin_is_dependency_failure(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    (tmp_path / "source.fits").unlink()
    with pytest.raises(SceneNotReadyError, match="source.fits"):
        prepare_scene_execution(card, path)


def test_remote_download_manifest_retains_scene_product_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, card = _card(tmp_path)
    data = document(card)
    data["selection"]["products"][0].pop("cached_asset_id")
    data["selection"]["products"][0]["data_uri"] = "mast:exact-v1"
    data["assets"] = {}
    remote = SceneCard.model_validate(data)
    launch = prepare_scene_execution(remote, path)

    def fake_download(uri, local_path, cache, verbose):
        Path(local_path).write_bytes(b"fits")
        return "COMPLETE", "", uri

    monkeypatch.setattr("galaxy.mast.Observations.download_file", fake_download)
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest, skipped = download_selected(launch.selection_manifest.candidates, cache)
    assert skipped == []
    assert manifest[0]["stable_product_identifier"] == "mast:exact-v1"


def test_cli_validate_and_run_use_scene_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    path, card = _card(tmp_path)
    assert cli.main(["validate-scene", "--scene", str(path)]) == 0
    captured = {}

    def fake_run(scene, workdir, mode):
        captured.update(scene=scene, workdir=workdir, mode=mode)
        class Result:
            class Artifacts:
                workdir = tmp_path / "run"
            artifacts = Artifacts()
        return Result()

    monkeypatch.setattr(cli, "run_scene_pipeline", fake_run)
    assert cli.main(["run", "--scene", str(path), "--mode", "compose-only"]) == 0
    assert captured == {"scene": str(path), "workdir": None, "mode": "compose-only"}
    assert "structurally valid" in capsys.readouterr().out


def test_cli_rejects_manifest_that_changes_scene_pins(tmp_path: Path) -> None:
    path, _ = _card(tmp_path)
    candidate = CandidateRecord(
        candidate_id="different", obsid=None, obs_id=None, product_filename="x.fits",
        data_uri="mast:x", mission="JWST", instrument="NIRCAM", detector=None,
        filter_name="F200W", product_type="SCIENCE", product_version=None,
        observation_date_start=None, observation_date_end=None, exposure_time=None,
        file_size=None, proposal_id=None, proposal_title=None, target_name=None,
        selection_rank=[], selected=True,
    )
    manifest_path = tmp_path / "selection.json"
    write_candidate_manifest(CandidateManifest(
        generated_at=NOW, config_path=str(path), selection_policy="all",
        max_observations_per_filter=1, candidates=[candidate], selection_inputs=SelectionInputs(),
    ), manifest_path)
    with pytest.raises(SystemExit):
        cli.main(["run", "--scene", str(path), "--selection", str(manifest_path)])


def test_cancelled_pipeline_does_not_append_success_history(tmp_path: Path) -> None:
    path, _ = _card(tmp_path)
    stages: list[str] = []

    def cancelled() -> bool:
        return bool(stages)

    with pytest.raises(PipelineCancelled, match="cancelled"):
        run_scene_pipeline(path, progress=stages.append, cancel_requested=cancelled)
    cancelled_card = load_scene(path)
    assert cancelled_card.renders is None
    assert all(asset.kind != "checkpoint_manifest" for asset in cancelled_card.assets.values())


def test_background_render_job_reports_success(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    job = start_render_job(path)
    assert job.wait(10)
    snapshot = job.snapshot()
    assert snapshot.phase.value == "succeeded"
    assert snapshot.launched_revision == card.content_revision
    assert snapshot.result is not None
    assert len(load_scene(path).renders) == 1


def test_background_render_job_cancels_at_runner_boundary(tmp_path: Path) -> None:
    path, card = _card(tmp_path)
    entered = __import__("threading").Event()
    release = __import__("threading").Event()

    def runner(card_path, *, progress, cancel_requested):
        progress("fixture stage")
        entered.set()
        release.wait(5)
        if cancel_requested():
            raise PipelineCancelled("cancelled at fixture boundary")
        raise AssertionError("cancellation was not delivered")

    job = start_render_job(path, runner=runner)
    assert entered.wait(5)
    job.cancel()
    release.set()
    assert job.wait(5)
    snapshot = job.snapshot()
    assert snapshot.phase.value == "cancelled"
    assert snapshot.launched_revision == card.content_revision
    assert snapshot.result is None
    assert load_scene(path).renders is None


def test_departure_requests_cancellation_and_waits_for_terminal_state(tmp_path: Path) -> None:
    path, _ = _card(tmp_path)
    entered = __import__("threading").Event()
    release = __import__("threading").Event()

    def runner(card_path, *, progress, cancel_requested):
        entered.set()
        release.wait(5)
        if cancel_requested():
            raise PipelineCancelled("departure boundary")
        raise AssertionError("departure failed to cancel the worker")

    job = start_render_job(path, runner=runner)
    assert entered.wait(5)
    assert request_cancellation_before_departure(job) is True
    release.set()
    assert job.wait(5)
    assert job.snapshot().phase.value == "cancelled"
    assert request_cancellation_before_departure(job) is False


def test_scene_pipeline_preserves_concurrent_metadata_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, _ = _card(tmp_path)
    real_run_pipeline = scene_pipeline_module.run_pipeline

    def run_then_edit(*args, **kwargs):
        artifacts = real_run_pipeline(*args, **kwargs)
        current = load_scene(path)
        save_scene(
            edit_scene(current, {"title": "Concurrent title"}),
            path,
            now="2026-09-14T12:01:00Z",
        )
        return artifacts

    monkeypatch.setattr(scene_pipeline_module, "run_pipeline", run_then_edit)
    result = run_scene_pipeline(path)

    assert result.card.title == "Concurrent title"
    assert load_scene(path) == result.card
    assert len(result.card.renders or []) == 1


def test_scene_pipeline_marks_completion_stale_after_concurrent_input_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from galaxy.scene_workflow import matching_render

    path, _ = _card(tmp_path)
    real_run_pipeline = scene_pipeline_module.run_pipeline

    def run_then_edit(*args, **kwargs):
        artifacts = real_run_pipeline(*args, **kwargs)
        current = load_scene(path)
        mapping = document(current.mapping)
        mapping["planes"][0]["rgb"]["red"] = 0.25
        save_scene(
            edit_scene(current, {"mapping": mapping}),
            path,
            now="2026-09-14T12:01:00Z",
        )
        return artifacts

    monkeypatch.setattr(scene_pipeline_module, "run_pipeline", run_then_edit)
    result = run_scene_pipeline(path)

    assert result.card.mapping.planes[0].rgb.red == 0.25
    assert len(result.card.renders or []) == 1
    assert matching_render(result.card) is None
    assert load_scene(path) == result.card

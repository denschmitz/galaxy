from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from galaxy import cli
from galaxy.scene_card import save_scene
from galaxy.scene_models import SceneCard
from galaxy.selection import CandidateManifest, CandidateRecord, SelectionInputs, write_candidate_manifest


NOW = "2026-09-14T12:00:00Z"


def _make_temp_dir() -> Path:
    root = Path.cwd() / ".tmp_test_cli"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    return path


def _write_scene(path: Path, *, selected: bool = False) -> SceneCard:
    data = {
        "document_type": "galaxy.scene_card", "schema_version": 1,
        "scene_id": str(uuid.uuid4()), "title": "CLI fixture",
        "created_at": NOW, "updated_at": NOW, "content_revision": 1,
        "target": {"ra_deg": 10.0, "dec_deg": 20.0, "coordinate_frame": "ICRS",
                   "region": {"kind": "circle", "radius_arcmin": 1.0}},
        "search": {"missions": ["JWST"], "observation_selection": "all",
                   "max_observations_per_filter": 1},
    }
    if selected:
        data["selection"] = {
            "products": [{"product_id": "cand-1", "data_uri": "mast:file", "filter": "F200W"}],
            "selected_product_ids": ["cand-1"],
        }
    return save_scene(SceneCard.model_validate(data), path, now=NOW)


def _record(candidate_id: str = "cand-1") -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id, obsid="1", obs_id="OBS1", product_filename="file.fits",
        data_uri="mast:file", mission="JWST", instrument="NIRCAM", detector="DET",
        filter_name="F200W", product_type="SCIENCE", product_version="v1",
        observation_date_start="1.0", observation_date_end="2.0", exposure_time=123.0,
        file_size=456, proposal_id="P1", proposal_title="Title", target_name="Target",
        selection_rank=[0, 0, [0], "file.fits"], selected=True,
        selected_reason="selected:user_manifest", user_selected=True,
    )


def test_discover_command_writes_candidate_manifest_and_summary(monkeypatch, capsys) -> None:
    temp = _make_temp_dir()
    scene = temp / "scene.json"
    output = temp / "candidates.json"
    _write_scene(scene)
    monkeypatch.setattr(cli, "discover_candidates", lambda *args, **kwargs: [_record()])

    assert cli.main(["discover", "--scene", str(scene), "--out", str(output)]) == 0
    assert "cand-1" in output.read_text()
    printed = capsys.readouterr().out
    assert "Candidate count: 1" in printed
    assert "Filters: F200W" in printed
    assert "Instruments: NIRCAM" in printed


def test_discover_command_applies_selection_overrides(monkeypatch) -> None:
    temp = _make_temp_dir()
    scene = temp / "scene.json"
    output = temp / "candidates.json"
    _write_scene(scene)
    captured = {}

    def fake_build(candidates, search, config_path, selection_inputs):
        captured["inputs"] = selection_inputs
        return CandidateManifest(NOW, config_path, "latest_per_filter", 1, [_record()], selection_inputs)

    monkeypatch.setattr(cli, "discover_candidates", lambda *args, **kwargs: [_record()])
    monkeypatch.setattr(cli, "build_candidate_manifest", fake_build)
    assert cli.main(["discover", "--scene", str(scene), "--out", str(output),
                     "--include-filter", "f200w", "--latest-per-filter", "--max-total", "1"]) == 0
    assert captured["inputs"].include_filters == {"F200W"}
    assert captured["inputs"].strategy == "latest_per_filter"
    assert captured["inputs"].max_total == 1


def test_run_passes_scene_workdir_and_mode(monkeypatch) -> None:
    temp = _make_temp_dir()
    scene = temp / "scene.json"
    _write_scene(scene, selected=True)
    captured = {}

    def fake_run(scene_arg, workdir, mode):
        captured.update(scene=scene_arg, workdir=workdir, mode=mode)
        return SimpleNamespace(artifacts=SimpleNamespace(workdir=Path(workdir)))

    monkeypatch.setattr(cli, "run_scene_pipeline", fake_run)
    workdir = temp / "artifacts"
    assert cli.main(["run", "--scene", str(scene), "--workdir", str(workdir),
                     "--mode", "compose-only"]) == 0
    assert captured == {"scene": str(scene), "workdir": str(workdir), "mode": "compose-only"}


def test_run_accepts_only_matching_optional_manifest(monkeypatch) -> None:
    temp = _make_temp_dir()
    scene = temp / "scene.json"
    _write_scene(scene, selected=True)
    manifest_path = temp / "selection.json"
    write_candidate_manifest(CandidateManifest(
        generated_at=NOW, config_path=str(scene), selection_policy="all",
        max_observations_per_filter=1, candidates=[_record()], selection_inputs=SelectionInputs(),
    ), manifest_path)

    class Result:
        class Artifacts:
            workdir = temp
        artifacts = Artifacts()

    monkeypatch.setattr(cli, "run_scene_pipeline", lambda *args, **kwargs: Result())
    assert cli.main(["run", "--scene", str(scene), "--selection", str(manifest_path)]) == 0

    write_candidate_manifest(CandidateManifest(
        generated_at=NOW, config_path=str(scene), selection_policy="all",
        max_observations_per_filter=1, candidates=[_record("replacement")],
        selection_inputs=SelectionInputs(),
    ), manifest_path)
    with pytest.raises(SystemExit):
        cli.main(["run", "--scene", str(scene), "--selection", str(manifest_path)])


def test_yaml_commands_are_not_part_of_normal_cli() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate-config", "--config", "legacy.yaml"])
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--config", "legacy.yaml", "--workdir", "out"])

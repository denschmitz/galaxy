from pathlib import Path
import uuid

import pytest
import yaml

from galaxy import cli
from galaxy.selection import CandidateManifest, CandidateRecord, SelectionInputs, write_candidate_manifest


def _make_temp_dir() -> Path:
    root = Path.cwd() / ".tmp_test_cli"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    return path


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "target": {"ra_deg": 10.0, "dec_deg": 20.0, "region": {"kind": "circle", "radius_arcmin": 1.0}},
                "canvas": {
                    "center": {"mode": "resolved_target"},
                    "pixel_scale_arcsec": 0.2,
                    "width": 32,
                    "height": 32,
                },
                "tone": {
                    "stretch": {
                        "red": {"kind": "asinh", "parameter": 4.0},
                        "green": {"kind": "asinh", "parameter": 4.0},
                        "blue": {"kind": "asinh", "parameter": 4.0},
                    },
                    "percentiles": {"black": 1.0, "white": 99.5},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _record() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand-1",
        obsid="1",
        obs_id="OBS1",
        product_filename="file.fits",
        data_uri="mast:file",
        mission="JWST",
        instrument="NIRCAM",
        detector="DET",
        filter_name="F200W",
        product_type="SCIENCE",
        product_version="v1",
        observation_date_start="1.0",
        observation_date_end="2.0",
        exposure_time=123.0,
        file_size=456,
        proposal_id="P1",
        proposal_title="Title",
        target_name="Target",
        selection_rank=[0, 0, [0], "file.fits"],
        selected=True,
        selected_reason="selected:user_manifest",
        user_selected=True,
    )


def test_discover_command_writes_candidate_manifest(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "config.yaml"
    out_path = temp_dir / "candidates.json"
    _write_config(config_path)

    monkeypatch.setattr(cli, "discover_candidates", lambda *args, **kwargs: [_record()])

    exit_code = cli.main(["discover", "--config", str(config_path), "--out", str(out_path)])
    assert exit_code == 0
    assert out_path.exists()
    assert "cand-1" in out_path.read_text(encoding="utf-8")


def test_discover_command_prints_summary(monkeypatch, capsys) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "config.yaml"
    out_path = temp_dir / "candidates.json"
    _write_config(config_path)

    monkeypatch.setattr(cli, "discover_candidates", lambda *args, **kwargs: [_record()])

    assert cli.main(["discover", "--config", str(config_path), "--out", str(out_path)]) == 0

    output = capsys.readouterr().out
    assert "Candidate count: 1" in output
    assert "Filters: F200W" in output
    assert "Instruments: NIRCAM" in output


def test_run_command_with_selection_manifest_passes_manifest_and_selection_inputs(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "config.yaml"
    workdir = temp_dir / "artifacts"
    selection_path = temp_dir / "candidates.json"
    _write_config(config_path)

    manifest = CandidateManifest(
        generated_at="2026-01-01T00:00:00+00:00",
        config_path=str(config_path),
        selection_policy="all",
        max_observations_per_filter=1,
        selection_inputs=SelectionInputs(),
        candidates=[_record()],
    )
    write_candidate_manifest(manifest, selection_path)

    captured = {}

    def fake_run_pipeline(config, workdir_arg, **kwargs):
        captured["workdir"] = workdir_arg
        captured["selection_manifest"] = kwargs["selection_manifest"]
        captured["selection_inputs"] = kwargs["selection_inputs"]

        class Artifacts:
            workdir = workdir_arg

        return Artifacts()

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    exit_code = cli.main(
        [
            "run",
            "--config",
            str(config_path),
            "--workdir",
            str(workdir),
            "--selection",
            str(selection_path),
            "--include-filter",
            "F200W",
            "--latest-per-filter",
            "--max-total",
            "1",
        ]
    )

    assert exit_code == 0
    assert captured["workdir"] == str(workdir)
    assert captured["selection_manifest"].candidates[0].candidate_id == "cand-1"
    assert captured["selection_inputs"].include_filters == {"F200W"}
    assert captured["selection_inputs"].strategy == "latest_per_filter"
    assert captured["selection_inputs"].max_total == 1


def test_run_command_list_filters_uses_manifest_summary_without_pipeline(monkeypatch, capsys) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "config.yaml"
    selection_path = temp_dir / "candidates.json"
    _write_config(config_path)

    manifest = CandidateManifest(
        generated_at="2026-01-01T00:00:00+00:00",
        config_path=str(config_path),
        selection_policy="all",
        max_observations_per_filter=1,
        selection_inputs=SelectionInputs(),
        candidates=[_record()],
    )
    write_candidate_manifest(manifest, selection_path)
    monkeypatch.setattr(cli, "run_pipeline", lambda *args, **kwargs: pytest.fail("run_pipeline should not be called"))

    assert (
        cli.main(
            [
                "run",
                "--config",
                str(config_path),
                "--workdir",
                str(temp_dir / "out"),
                "--selection",
                str(selection_path),
                "--list-filters",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Filters: F200W" in output

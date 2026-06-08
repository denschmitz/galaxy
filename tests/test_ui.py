from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time
import uuid

import pytest

from galaxy.config import GalaxyConfig, MappingConfig, ToneConfig
from galaxy.selection import CandidateManifest, SelectionInputs
from galaxy.ui import (
    DISCOVERY_CACHE_MAX_AGE,
    _associated_project_path,
    _default_project_save_path,
    _discovery_cache_path,
    _discovery_query_key,
    _discover_default_input,
    _load_or_query_discovery_manifest,
    _looks_like_candidate_manifest,
    _parse_style_document,
    _preview_branch_paths,
    _project_from_preview_state,
    _resolve_input_candidate,
)


def _make_temp_dir() -> Path:
    root = Path.cwd() / ".tmp_test_ui"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    return path


def test_parse_style_document_accepts_yaml_mapping() -> None:
    style = _parse_style_document(
        """
mapping:
  planes:
    - plane: red_plane
      rgb:
        red: 1.5
        green: 0.0
        blue: 0.0
tone:
  percentiles:
    black: 1.0
    white: 99.5
enabled_planes:
  - red_plane
"""
    )
    assert style["mapping"]["planes"][0]["plane"] == "red_plane"


def test_parse_style_document_rejects_non_mapping() -> None:
    with pytest.raises(ValueError):
        _parse_style_document("- just\n- a\n- list\n")


def test_looks_like_candidate_manifest() -> None:
    temp_dir = _make_temp_dir()
    path = temp_dir / "candidates.json"
    path.write_text('{"candidates": []}', encoding="utf-8")
    assert _looks_like_candidate_manifest(path) is True


def _config_with_box(width_arcmin: float = 1.5, height_arcmin: float = 1.5) -> GalaxyConfig:
    return GalaxyConfig.model_validate(
        {
            "target": {
                "name": "Pillars of Creation",
                "ra_deg": 274.7003,
                "dec_deg": -13.8067,
                "region": {"kind": "box", "width_arcmin": width_arcmin, "height_arcmin": height_arcmin},
            },
            "search": {
                "missions": ["HST", "JWST"],
                "filters": ["F200W"],
                "product_types": ["SCIENCE"],
            },
            "canvas": {
                "center": {"mode": "explicit", "ra_deg": 274.7003, "dec_deg": -13.8067},
                "pixel_scale_arcsec": 0.08,
                "width": 5000,
                "height": 5000,
            },
            "mapping": {
                "planes": [
                    {"plane": "plane_a", "rgb": {"red": 1.0, "green": 1.0, "blue": 1.0}}
                ]
            },
            "tone": {
                "stretch": {
                    "red": {"kind": "asinh", "parameter": 4.0},
                    "green": {"kind": "asinh", "parameter": 4.0},
                    "blue": {"kind": "asinh", "parameter": 4.0},
                },
                "percentiles": {"black": 0.0, "white": 100.0},
            },
        }
    )


def test_discovery_query_key_changes_when_box_changes() -> None:
    key_a = _discovery_query_key(_config_with_box(1.5, 1.5))
    key_b = _discovery_query_key(_config_with_box(2.0, 1.5))

    assert key_a != key_b


def test_load_or_query_discovery_manifest_uses_disk_cache(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "examples" / "pillars.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("target: {}\n", encoding="utf-8")
    config = _config_with_box()
    query_key = _discovery_query_key(config)
    cache_path = _discovery_cache_path(config_path)
    manifest = CandidateManifest(
        generated_at="2026-01-01T00:00:00Z",
        config_path=str(config_path),
        selection_policy="deepest_per_filter",
        max_observations_per_filter=1,
        selection_inputs=SelectionInputs(),
        candidates=[],
    )
    payload = manifest.to_dict()
    payload["discovery_cache_key"] = query_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    monkeypatch.setattr("galaxy.ui.discover_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not query MAST")))

    loaded = _load_or_query_discovery_manifest(config_path, config, query_key)

    assert loaded.generated_at == manifest.generated_at
    assert loaded.config_path == str(config_path)


def test_resolve_input_candidate_prefers_exported_planes_in_workdir() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    planes_path = workdir / "exported_planes.fits"
    planes_path.write_text("fits", encoding="utf-8")
    (workdir / "project.yaml").write_text("format_revision: 1\n", encoding="utf-8")

    assert _resolve_input_candidate(workdir) == planes_path


def test_resolve_input_candidate_keeps_explicit_project_file() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    project_path = workdir / "project.yaml"
    project_path.write_text("format_revision: 1\n", encoding="utf-8")
    planes_path = workdir / "exported_planes.fits"
    planes_path.write_text("fits", encoding="utf-8")

    assert _resolve_input_candidate(project_path) == project_path


def test_associated_project_path_uses_project_yaml_for_preview_exports() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    project_path = workdir / "project.yaml"
    planes_path = workdir / "exported_planes.fits"
    project_path.write_text("format_revision: 1\n", encoding="utf-8")
    planes_path.write_text("fits", encoding="utf-8")

    assert _associated_project_path(planes_path) == project_path


def test_load_or_query_discovery_manifest_requeries_when_cache_is_stale(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "examples" / "pillars.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("target: {}\n", encoding="utf-8")
    config = _config_with_box()
    query_key = _discovery_query_key(config)
    cache_path = _discovery_cache_path(config_path)
    stale_generated_at = (datetime.now(timezone.utc) - DISCOVERY_CACHE_MAX_AGE - timedelta(days=1)).isoformat()
    manifest = CandidateManifest(
        generated_at=stale_generated_at,
        config_path=str(config_path),
        selection_policy="deepest_per_filter",
        max_observations_per_filter=1,
        selection_inputs=SelectionInputs(),
        candidates=[],
    )
    payload = manifest.to_dict()
    payload["discovery_cache_key"] = query_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    monkeypatch.setattr("galaxy.ui.resolve_target", lambda target: type("Resolved", (), {"coord": object()})())
    monkeypatch.setattr("galaxy.ui.region_to_mast_shape", lambda region, coord: ("circle", {"ra": 1.0, "dec": 2.0, "radius": 0.1}))
    monkeypatch.setattr("galaxy.ui.discover_candidates", lambda *args, **kwargs: [])

    loaded = _load_or_query_discovery_manifest(config_path, config, query_key)

    assert loaded.generated_at != stale_generated_at


def test_load_or_query_discovery_manifest_allows_explicit_stale_reuse(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    config_path = temp_dir / "examples" / "pillars.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("target: {}\n", encoding="utf-8")
    config = _config_with_box()
    query_key = _discovery_query_key(config)
    cache_path = _discovery_cache_path(config_path)
    stale_generated_at = (datetime.now(timezone.utc) - DISCOVERY_CACHE_MAX_AGE - timedelta(days=1)).isoformat()
    manifest = CandidateManifest(
        generated_at=stale_generated_at,
        config_path=str(config_path),
        selection_policy="deepest_per_filter",
        max_observations_per_filter=1,
        selection_inputs=SelectionInputs(),
        candidates=[],
    )
    payload = manifest.to_dict()
    payload["discovery_cache_key"] = query_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    monkeypatch.setattr("galaxy.ui.discover_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not query MAST")))

    loaded = _load_or_query_discovery_manifest(config_path, config, query_key, allow_stale=True)

    assert loaded.generated_at == stale_generated_at


def test_default_project_save_path_uses_project_yaml_in_artifact_directory() -> None:
    source = Path("C:/Data/dev/galaxy/artifacts/pillars/project.yaml")
    assert _default_project_save_path(source) == Path("C:/Data/dev/galaxy/artifacts/pillars/project.yaml")


def test_project_from_preview_state_persists_mapping_tone_and_plane_enablement() -> None:
    config = _config_with_box().model_copy(
        update={
            "planes": _config_with_box().planes.model_copy(update={"enabled_filters": ["F200W"], "disabled_plane_ids": []})
        }
    )
    metadata = {
        "plane_a": {"filter": "F200W"},
        "plane_b": {"filter": "F090W"},
    }
    mapping = MappingConfig.model_validate({"planes": [{"plane": "plane_b", "rgb": {"blue": 1.0}}]})
    tone = ToneConfig.model_validate(
        {
            "stretch": {
                "red": {"kind": "gamma", "parameter": 2.0},
                "green": {"kind": "asinh", "parameter": 4.0},
                "blue": {"kind": "asinh", "parameter": 5.0},
            },
            "percentiles": {"black": 1.0, "white": 99.0},
        }
    )

    updated = _project_from_preview_state(config, {"plane_b"}, mapping, tone, metadata)

    assert updated.planes.disabled_plane_ids == ["plane_a"]
    assert updated.planes.enabled_filters == ["F090W"]
    assert updated.mapping.planes[0].plane == "plane_b"
    assert updated.tone.stretch.red.kind == "gamma"


def test_resolve_input_path_uses_environment_override(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    planes_path = workdir / "exported_planes.fits"
    planes_path.write_text("fits", encoding="utf-8")

    monkeypatch.setenv("GALAXY_UI_INPUT_PATH", str(workdir))
    monkeypatch.setattr("sys.argv", ["ui.py"])

    from galaxy.ui import _resolve_input_path

    assert _resolve_input_path() == planes_path


def test_discover_default_input_prefers_latest_exported_planes() -> None:
    temp_dir = _make_temp_dir()
    first = temp_dir / "artifacts" / "one"
    second = temp_dir / "artifacts" / "two"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    first_path = first / "exported_planes.fits"
    second_path = second / "exported_planes.fits"
    first_path.write_text("old", encoding="utf-8")
    second_path.write_text("new", encoding="utf-8")
    base = time.time()
    os.utime(first_path, (base - 10, base - 10))
    os.utime(second_path, (base, base))

    assert _discover_default_input(temp_dir) == second_path


def test_preview_branch_paths_discovers_original_and_deconvolved_exports() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    original = workdir / "exported_planes.fits"
    deconvolved = workdir / "exported_planes_deconvolved.fits"
    original.write_text("fits", encoding="utf-8")
    deconvolved.write_text("fits", encoding="utf-8")

    branches = _preview_branch_paths(workdir)

    assert branches == {"original": original, "deconvolved": deconvolved}


def test_resolve_input_candidate_accepts_direct_deconvolved_export() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    deconvolved = workdir / "exported_planes_deconvolved.fits"
    deconvolved.write_text("fits", encoding="utf-8")

    assert _resolve_input_candidate(deconvolved) == deconvolved


def test_discover_default_input_prefers_original_export_over_newer_deconvolved_export() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    original = workdir / "exported_planes.fits"
    deconvolved = workdir / "exported_planes_deconvolved.fits"
    original.write_text("original", encoding="utf-8")
    deconvolved.write_text("deconvolved", encoding="utf-8")
    base = time.time()
    os.utime(original, (base - 20, base - 20))
    os.utime(deconvolved, (base, base))

    assert _discover_default_input(temp_dir) == original


def test_resolve_input_path_falls_back_to_workspace_artifact(monkeypatch) -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    planes_path = workdir / "exported_planes.fits"
    planes_path.write_text("fits", encoding="utf-8")

    monkeypatch.delenv("GALAXY_UI_INPUT_PATH", raising=False)
    monkeypatch.setattr("sys.argv", ["ui.py"])
    monkeypatch.setattr("galaxy.ui.Path.cwd", lambda: temp_dir)

    from galaxy.ui import _resolve_input_path

    assert _resolve_input_path() == planes_path

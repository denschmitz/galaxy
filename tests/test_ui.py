from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest

from galaxy.config import GalaxyConfig
from galaxy.selection import CandidateManifest, SelectionInputs
from galaxy.ui import (
    DISCOVERY_CACHE_MAX_AGE,
    _discovery_cache_path,
    _discovery_query_key,
    _load_or_query_discovery_manifest,
    _looks_like_candidate_manifest,
    _parse_style_document,
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
  channels:
    red:
      - plane: red_plane
        weight: 1.5
tone:
  percentiles:
    black: 1.0
    white: 99.5
enabled_planes:
  - red_plane
"""
    )
    assert style["mapping"]["channels"]["red"][0]["plane"] == "red_plane"


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
                "channels": {
                    "red": [{"plane": "plane_a", "weight": 1.0}],
                    "green": [{"plane": "plane_a", "weight": 1.0}],
                    "blue": [{"plane": "plane_a", "weight": 1.0}],
                }
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
    (workdir / "run_config.yaml").write_text("config: true\n", encoding="utf-8")

    assert _resolve_input_candidate(workdir) == planes_path


def test_resolve_input_candidate_redirects_run_config_to_exported_planes() -> None:
    temp_dir = _make_temp_dir()
    workdir = temp_dir / "artifacts" / "pillars"
    workdir.mkdir(parents=True)
    run_config = workdir / "run_config.yaml"
    run_config.write_text("config: true\n", encoding="utf-8")
    planes_path = workdir / "exported_planes.fits"
    planes_path.write_text("fits", encoding="utf-8")

    assert _resolve_input_candidate(run_config) == planes_path


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

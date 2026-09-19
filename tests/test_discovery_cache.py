from __future__ import annotations

from datetime import datetime, timezone

from galaxy.discovery_cache import (
    candidate_cache_path, load_cached_candidates, save_cached_candidates,
)
from galaxy.scene_workflow import draft_from_target
from galaxy.selection import CandidateManifest, CandidateRecord


def _manifest(timestamp: str) -> CandidateManifest:
    candidate = CandidateRecord(
        candidate_id="mast:one", obsid="1", obs_id="obs-1", product_filename="one.fits",
        data_uri="mast:one", mission="JWST", instrument="NIRCAM", detector="NRCA1",
        filter_name="F200W", product_type="SCIENCE", product_version="1",
        observation_date_start=None, observation_date_end=None, exposure_time=1.0,
        file_size=2, proposal_id="123", proposal_title="Fixture", target_name="M1",
        selection_rank=[], selected=True,
    )
    return CandidateManifest(
        generated_at=timestamp, config_path=None, selection_policy="all",
        max_observations_per_filter=1, candidates=[candidate],
    )


def _card():
    return draft_from_target(
        name="M1", ra_deg=83.633, dec_deg=22.014,
        width_arcmin=2.0, height_arcmin=2.0,
    )


def test_candidate_cache_round_trip_and_query_key(tmp_path) -> None:
    card = _card()
    saved = save_cached_candidates(tmp_path, card, _manifest("2026-09-14T12:00:00Z"))
    assert saved.path == candidate_cache_path(tmp_path, card)
    loaded = load_cached_candidates(
        tmp_path, card, now=datetime(2026, 9, 15, tzinfo=timezone.utc)
    )
    assert loaded is not None
    assert loaded.stale is False
    assert loaded.manifest.candidates[0].candidate_id == "mast:one"
    changed = draft_from_target(
        name="M1", ra_deg=83.633, dec_deg=22.014,
        width_arcmin=3.0, height_arcmin=2.0,
    )
    assert candidate_cache_path(tmp_path, changed) != saved.path


def test_candidate_cache_marks_results_older_than_six_months_stale(tmp_path) -> None:
    card = _card()
    save_cached_candidates(tmp_path, card, _manifest("2026-01-01T00:00:00Z"))
    loaded = load_cached_candidates(
        tmp_path, card, now=datetime(2026, 9, 14, tzinfo=timezone.utc)
    )
    assert loaded is not None
    assert loaded.stale is True

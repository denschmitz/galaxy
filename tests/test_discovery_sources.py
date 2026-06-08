from datetime import datetime, timezone

import pytest

from galaxy.discovery_sources import (
    LATEST_JWST_RELEASE_TRACKER_URL,
    DiscoveryAlignment,
    DiscoveryHint,
    DiscoverySourceQuery,
)


def _retrieved_at() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_discovery_hint_defaults_to_noop_alignment() -> None:
    hint = DiscoveryHint(
        source_name="jwst_latest_release",
        source_url=LATEST_JWST_RELEASE_TRACKER_URL,
        retrieved_at=_retrieved_at(),
        target_name="M82",
    )

    assert hint.alignment.rotation_deg == 0.0
    assert hint.alignment.is_noop is True


def test_discovery_alignment_accepts_full_turn_rotation() -> None:
    alignment = DiscoveryAlignment(rotation_deg=360.0)

    assert alignment.rotation_deg == 360.0
    assert alignment.is_noop is True


@pytest.mark.parametrize("rotation_deg", [-0.1, 360.1])
def test_discovery_alignment_rejects_out_of_bounds_rotation(rotation_deg: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 360"):
        DiscoveryAlignment(rotation_deg=rotation_deg)


def test_discovery_hint_normalizes_instruments_and_filters() -> None:
    hint = DiscoveryHint(
        source_name="jwst_latest_release",
        source_url=LATEST_JWST_RELEASE_TRACKER_URL,
        retrieved_at=_retrieved_at(),
        instruments=("nircam", "miri"),
        filters=("f200w", "f770w"),
    )

    assert hint.instruments == ("NIRCAM", "MIRI")
    assert hint.filters == ("F200W", "F770W")


def test_discovery_hint_requires_coordinate_pair() -> None:
    with pytest.raises(ValueError, match="ra_deg and dec_deg"):
        DiscoveryHint(
            source_name="jwst_latest_release",
            source_url=LATEST_JWST_RELEASE_TRACKER_URL,
            retrieved_at=_retrieved_at(),
            ra_deg=10.0,
        )


def test_discovery_source_query_rejects_non_positive_max_results() -> None:
    with pytest.raises(ValueError, match="max_results"):
        DiscoverySourceQuery(max_results=0)

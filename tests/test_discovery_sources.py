from datetime import datetime, timezone

import pytest

from galaxy.discovery_sources import (
    LATEST_JWST_RELEASE_CREDIT,
    LATEST_JWST_RELEASE_CSV_URL,
    LATEST_JWST_RELEASE_TRACKER_URL,
    DiscoveryAlignment,
    DiscoveryHint,
    DiscoverySourceQuery,
    YuvalHarpazLatestReleaseSource,
    discover_isolated,
)
from galaxy.scene_workflow import draft_from_discovery_hint


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


CSV = """obsid,proposal_id,proposal_pi,target_name,instrument_name,obs_title,jpegURL,t_max,t_obs_release,dataURL
2,222,PI Two,NGC-2,MIRI/IMAGE,Second target,,2026-09-11 02:00:00,2026-09-12 03:00:00,mast:JWST/product/two.fits
1,111,PI One,NGC_1,NIRCAM/IMAGE,First target,mast:JWST/product/jw00001_nircam_clear-f200w_i2d.jpg,2026-09-12 02:00:00,2026-09-13 03:00:00,mast:JWST/product/one.fits
"""


def test_latest_release_adapter_filters_attributes_and_preserves_rows() -> None:
    seen: list[str] = []
    source = YuvalHarpazLatestReleaseSource(
        fetch_csv=lambda url: seen.append(url) or CSV,
        now=_retrieved_at,
    )
    hints = source.discover(DiscoverySourceQuery(text="ngc1", date_start="2026-09-13"))
    assert seen == [LATEST_JWST_RELEASE_CSV_URL]
    assert len(hints) == 1
    hint = hints[0]
    assert hint.target_name == "NGC_1"
    assert hint.instruments == ("NIRCAM",)
    assert hint.filters == ("F200W",)
    assert hint.preview_url == "https://mast.stsci.edu/portal/Download/file/JWST/product/jw00001_nircam_clear-f200w_i2d.jpg"
    assert hint.credit == LATEST_JWST_RELEASE_CREDIT
    assert hint.extracted_metadata["obsid"] == "1"


def test_latest_release_adapter_keeps_missing_thumbnail_selectable() -> None:
    hints = YuvalHarpazLatestReleaseSource(fetch_csv=lambda _: CSV, now=_retrieved_at).discover(
        DiscoverySourceQuery(text="Second", max_results=1)
    )
    assert len(hints) == 1
    assert hints[0].preview_url is None
    assert hints[0].data_url.endswith("/JWST/product/two.fits")


def test_external_source_failure_is_isolated() -> None:
    good = YuvalHarpazLatestReleaseSource(fetch_csv=lambda _: CSV, now=_retrieved_at)
    class Broken:
        name = "broken_tracker"

        def discover(self, query: DiscoverySourceQuery) -> list[DiscoveryHint]:
            raise RuntimeError("offline")

    bad = Broken()
    batch = discover_isolated([bad, good], DiscoverySourceQuery(max_results=1))
    assert len(batch.hints) == 1
    assert batch.failures[0].source_name == "broken_tracker"
    assert batch.failures[0].message == "offline"


def test_hint_conversion_records_provenance_without_pinning_tracker_product() -> None:
    hint = YuvalHarpazLatestReleaseSource(fetch_csv=lambda _: CSV, now=_retrieved_at).discover(
        DiscoverySourceQuery(text="First")
    )[0]
    card = draft_from_discovery_hint(hint)
    assert card.discovery.sources[0].source_url == LATEST_JWST_RELEASE_TRACKER_URL
    assert card.discovery.sources[0].extracted_metadata["dataURL"].startswith("mast:")
    assert card.thumbnail_asset_id == "discovery-thumbnail"
    assert card.assets["discovery-thumbnail"].credit == LATEST_JWST_RELEASE_CREDIT
    assert card.selection is None

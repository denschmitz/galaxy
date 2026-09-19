from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Protocol


LATEST_JWST_RELEASE_TRACKER_URL = "https://yuval-harpaz.github.io/astro/jwst_latest_release.html"
LATEST_JWST_RELEASE_CSV_URL = (
    "https://raw.githubusercontent.com/yuval-harpaz/astro/refs/heads/main/docs/latest.csv"
)
LATEST_JWST_RELEASE_CREDIT = "STScI/MAST; NASA, ESA, CSA; tracker by Yuval Harpaz"


@dataclass(frozen=True, slots=True)
class DiscoveryAlignment:
    rotation_deg: float = 0.0

    def __post_init__(self) -> None:
        rotation = float(self.rotation_deg)
        if rotation < 0.0 or rotation > 360.0:
            raise ValueError("discovery alignment rotation_deg must be between 0 and 360 degrees inclusive")
        object.__setattr__(self, "rotation_deg", rotation)

    @property
    def is_noop(self) -> bool:
        return self.rotation_deg in {0.0, 360.0}


@dataclass(frozen=True, slots=True)
class DiscoveryHint:
    source_name: str
    source_url: str
    retrieved_at: datetime
    target_name: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    proposal_id: str | None = None
    observation_date: str | None = None
    instruments: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    preview_url: str | None = None
    data_url: str | None = None
    credit: str | None = None
    notes: str | None = None
    extracted_metadata: dict[str, str] = field(default_factory=dict)
    alignment: DiscoveryAlignment = field(default_factory=DiscoveryAlignment)

    def __post_init__(self) -> None:
        if not self.source_name:
            raise ValueError("discovery hint source_name is required")
        if not self.source_url:
            raise ValueError("discovery hint source_url is required")
        if (self.ra_deg is None) != (self.dec_deg is None):
            raise ValueError("discovery hint ra_deg and dec_deg must be provided together")
        if not isinstance(self.alignment, DiscoveryAlignment):
            raise TypeError("discovery hint alignment must be a DiscoveryAlignment")
        object.__setattr__(self, "instruments", tuple(str(item).upper() for item in self.instruments))
        object.__setattr__(self, "filters", tuple(str(item).upper() for item in self.filters))
        object.__setattr__(self, "extracted_metadata", dict(self.extracted_metadata))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["retrieved_at"] = self.retrieved_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class DiscoverySourceQuery:
    text: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    max_results: int | None = None

    def __post_init__(self) -> None:
        if self.max_results is not None and self.max_results < 1:
            raise ValueError("discovery source max_results must be at least 1")


class DiscoverySource(Protocol):
    name: str

    def discover(self, query: DiscoverySourceQuery) -> list[DiscoveryHint]:
        ...


@dataclass(frozen=True, slots=True)
class DiscoverySourceFailure:
    source_name: str
    message: str


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    hints: tuple[DiscoveryHint, ...]
    failures: tuple[DiscoverySourceFailure, ...]


def discover_isolated(
    sources: list[DiscoverySource], query: DiscoverySourceQuery
) -> DiscoveryBatch:
    """Run independent hint sources without making one source a discovery dependency."""
    hints: list[DiscoveryHint] = []
    failures: list[DiscoverySourceFailure] = []
    for source in sources:
        try:
            hints.extend(source.discover(query))
        except Exception as exc:
            failures.append(DiscoverySourceFailure(source.name, str(exc)))
    return DiscoveryBatch(tuple(hints), tuple(failures))


class YuvalHarpazLatestReleaseSource:
    """Adapter for the tracker CSV linked by the supported latest-release page."""

    name = "jwst_latest_release"
    required_columns = {
        "obsid", "proposal_id", "target_name", "instrument_name", "obs_title",
        "jpegURL", "t_max", "t_obs_release", "dataURL",
    }

    def __init__(
        self,
        *,
        fetch_csv: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetch_csv = fetch_csv or _fetch_csv
        self._now = now or (lambda: datetime.now(timezone.utc))

    def discover(self, query: DiscoverySourceQuery) -> list[DiscoveryHint]:
        retrieved_at = self._now()
        if retrieved_at.tzinfo is None:
            raise ValueError("discovery retrieval time must include a timezone")
        reader = csv.DictReader(io.StringIO(self._fetch_csv(LATEST_JWST_RELEASE_CSV_URL)))
        columns = set(reader.fieldnames or [])
        missing = sorted(self.required_columns - columns)
        if missing:
            raise ValueError(f"latest-release CSV is missing columns: {', '.join(missing)}")
        rows = [dict(row) for row in reader]
        rows.sort(key=lambda row: row.get("t_obs_release", ""), reverse=True)
        hints = [self._hint(row, retrieved_at) for row in rows if self._matches(row, query)]
        return hints[:query.max_results] if query.max_results is not None else hints

    def _matches(self, row: dict[str, str | None], query: DiscoverySourceQuery) -> bool:
        if query.text:
            needle = _normalized(query.text)
            values = (row.get("target_name"), row.get("obs_title"), row.get("proposal_id"))
            if not any(needle in _normalized(value or "") for value in values):
                return False
        released = _row_date(row.get("t_obs_release"))
        if query.date_start and released < date.fromisoformat(query.date_start):
            return False
        if query.date_end and released > date.fromisoformat(query.date_end):
            return False
        return True

    def _hint(self, row: dict[str, str | None], retrieved_at: datetime) -> DiscoveryHint:
        metadata = {key: value.strip() for key, value in row.items() if value and value.strip()}
        preview = _mast_url(metadata.get("jpegURL"))
        data_url = _mast_url(metadata.get("dataURL"))
        instrument = metadata.get("instrument_name", "").split("/", 1)[0]
        filter_name = _filter_from_url(metadata.get("jpegURL", ""))
        return DiscoveryHint(
            source_name=self.name,
            source_url=LATEST_JWST_RELEASE_TRACKER_URL,
            retrieved_at=retrieved_at.astimezone(timezone.utc),
            target_name=metadata.get("target_name"),
            proposal_id=metadata.get("proposal_id"),
            observation_date=metadata.get("t_max"),
            instruments=(instrument,) if instrument else (),
            filters=(filter_name,) if filter_name else (),
            preview_url=preview,
            data_url=data_url,
            credit=LATEST_JWST_RELEASE_CREDIT,
            notes=metadata.get("obs_title"),
            extracted_metadata=metadata,
        )


def _fetch_csv(url: str) -> str:
    import requests
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _mast_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("mast:"):
        return value.replace("mast:", "https://mast.stsci.edu/portal/Download/file/", 1)
    return value


def _filter_from_url(value: str) -> str | None:
    match = re.search(r"(?:^|[-_])f([a-z0-9]+)(?=[-_])", value, flags=re.IGNORECASE)
    return f"F{match.group(1).upper()}" if match else None


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _row_date(value: str | None) -> date:
    if not value:
        raise ValueError("latest-release row has no t_obs_release")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()

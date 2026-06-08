from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol


LATEST_JWST_RELEASE_TRACKER_URL = "https://yuval-harpaz.github.io/astro/jwst_latest_release.html"


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
    notes: str | None = None
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

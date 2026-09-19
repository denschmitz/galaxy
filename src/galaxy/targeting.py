from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Callable

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates.name_resolve import NameResolveError

from galaxy.processing_config import BoxRegion, CircleRegion, PolygonRegion, TargetConfig


@dataclass(slots=True)
class ResolvedTarget:
    coord: SkyCoord
    source: str
    region: dict[str, Any]


class ResolverStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ResolverMatch:
    label: str
    ra_deg: float
    dec_deg: float


@dataclass(frozen=True, slots=True)
class ResolverOutcome:
    status: ResolverStatus
    source: str
    matches: tuple[ResolverMatch, ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        minimum = {ResolverStatus.RESOLVED: 1, ResolverStatus.AMBIGUOUS: 2}.get(self.status)
        if minimum is not None and len(self.matches) < minimum:
            raise ValueError(f"{self.status.value} resolver outcome requires {minimum} match(es)")
        if self.status in {ResolverStatus.UNRESOLVED, ResolverStatus.FAILED} and self.matches:
            raise ValueError(f"{self.status.value} resolver outcome cannot contain matches")


NameResolver = Callable[[str], ResolverOutcome]


def resolve_name(name: str, resolver: NameResolver | None = None) -> ResolverOutcome:
    query = name.strip()
    if not query:
        raise ValueError("target name is required")
    if resolver is not None:
        return resolver(query)
    try:
        coord = SkyCoord.from_name(query).icrs
    except NameResolveError as exc:
        return ResolverOutcome(ResolverStatus.UNRESOLVED, "astropy-name-resolver", message=str(exc))
    except Exception as exc:
        return ResolverOutcome(ResolverStatus.FAILED, "astropy-name-resolver", message=str(exc))
    return ResolverOutcome(
        ResolverStatus.RESOLVED,
        "astropy-name-resolver",
        (ResolverMatch(query, float(coord.ra.deg), float(coord.dec.deg)),),
    )


def resolve_target(target: TargetConfig) -> ResolvedTarget:
    if target.ra_deg is not None and target.dec_deg is not None:
        coord = SkyCoord(target.ra_deg * u.deg, target.dec_deg * u.deg, frame="icrs")
        source = "explicit-decimal"
    elif target.ra and target.dec:
        coord = SkyCoord(target.ra, target.dec, unit=(u.hourangle, u.deg), frame="icrs")
        source = "explicit-sexagesimal"
    elif target.name:
        outcome = resolve_name(target.name)
        if outcome.status is not ResolverStatus.RESOLVED:
            detail = f": {outcome.message}" if outcome.message else ""
            raise ValueError(f"target name resolution {outcome.status.value}{detail}")
        match = outcome.matches[0]
        coord = SkyCoord(match.ra_deg * u.deg, match.dec_deg * u.deg, frame="icrs")
        source = outcome.source
    else:
        raise ValueError("target must specify either name, decimal coordinates, or sexagesimal coordinates")
    return ResolvedTarget(coord=coord.icrs, source=source, region=region_to_record(target.region))


def region_to_record(region: CircleRegion | BoxRegion | PolygonRegion) -> dict[str, Any]:
    return region.model_dump(mode="json")


def region_to_mast_shape(region: CircleRegion | BoxRegion | PolygonRegion, center: SkyCoord) -> tuple[str, dict[str, Any]]:
    if region.kind == "circle":
        return "circle", {"ra": center.ra.deg, "dec": center.dec.deg, "radius": region.radius_arcmin / 60.0}
    if region.kind == "box":
        half_width_deg = region.width_arcmin / 120.0
        half_height_deg = region.height_arcmin / 120.0
        radius_deg = math.hypot(half_width_deg, half_height_deg)
        return "circle", {
            "ra": center.ra.deg,
            "dec": center.dec.deg,
            "radius": radius_deg,
            "source_region": "box-approximated-as-circle",
            "width": region.width_arcmin / 60.0,
            "height": region.height_arcmin / 60.0,
        }
    if region.kind == "polygon":
        return "polygon", {"coordinates": region.vertices}
    raise ValueError(f"unsupported region kind: {region.kind}")

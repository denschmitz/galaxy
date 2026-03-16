from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import astropy.units as u
from astropy.coordinates import SkyCoord

from galaxy.config import BoxRegion, CircleRegion, PolygonRegion, TargetConfig


@dataclass(slots=True)
class ResolvedTarget:
    coord: SkyCoord
    source: str
    region: dict[str, Any]


def resolve_target(target: TargetConfig) -> ResolvedTarget:
    if target.name:
        coord = SkyCoord.from_name(target.name)
        source = "astropy-name-resolver"
    elif target.ra_deg is not None and target.dec_deg is not None:
        coord = SkyCoord(target.ra_deg * u.deg, target.dec_deg * u.deg, frame="icrs")
        source = "explicit-decimal"
    else:
        coord = SkyCoord(target.ra, target.dec, unit=(u.hourangle, u.deg), frame="icrs")
        source = "explicit-sexagesimal"
    return ResolvedTarget(coord=coord.icrs, source=source, region=region_to_record(target.region))


def region_to_record(region: CircleRegion | BoxRegion | PolygonRegion) -> dict[str, Any]:
    return region.model_dump(mode="json")


def region_to_mast_shape(region: CircleRegion | BoxRegion | PolygonRegion, center: SkyCoord) -> tuple[str, dict[str, Any]]:
    if isinstance(region, CircleRegion):
        return "circle", {"ra": center.ra.deg, "dec": center.dec.deg, "radius": region.radius_arcmin / 60.0}
    if isinstance(region, BoxRegion):
        return "box", {
            "ra": center.ra.deg,
            "dec": center.dec.deg,
            "width": region.width_arcmin / 60.0,
            "height": region.height_arcmin / 60.0,
        }
    return "polygon", {"coordinates": region.vertices}

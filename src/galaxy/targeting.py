from __future__ import annotations

from dataclasses import dataclass
import math
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
    if target.ra_deg is not None and target.dec_deg is not None:
        coord = SkyCoord(target.ra_deg * u.deg, target.dec_deg * u.deg, frame="icrs")
        source = "explicit-decimal"
    elif target.ra and target.dec:
        coord = SkyCoord(target.ra, target.dec, unit=(u.hourangle, u.deg), frame="icrs")
        source = "explicit-sexagesimal"
    elif target.name:
        coord = SkyCoord.from_name(target.name)
        source = "astropy-name-resolver"
    else:
        raise ValueError("target must specify either name, decimal coordinates, or sexagesimal coordinates")
    return ResolvedTarget(coord=coord.icrs, source=source, region=region_to_record(target.region))


def region_to_record(region: CircleRegion | BoxRegion | PolygonRegion) -> dict[str, Any]:
    return region.model_dump(mode="json")


def region_to_mast_shape(region: CircleRegion | BoxRegion | PolygonRegion, center: SkyCoord) -> tuple[str, dict[str, Any]]:
    if isinstance(region, CircleRegion):
        return "circle", {"ra": center.ra.deg, "dec": center.dec.deg, "radius": region.radius_arcmin / 60.0}
    if isinstance(region, BoxRegion):
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
    return "polygon", {"coordinates": region.vertices}

"""Deterministic canvas fitting for the valid support of selected FITS planes."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.wcs.utils import proj_plane_pixel_scales
import numpy as np
from scipy.spatial import ConvexHull

from .fitsio import FITSPlane, load_fits_plane
from .processing_config import CanvasConfig
from .reprojection import build_output_wcs


MAX_PREVIEW_DIMENSION = 2048


@dataclass(frozen=True, slots=True)
class FramingDiagnostics:
    component_count: int
    angular_span_deg: float
    frame_width_deg: float
    frame_height_deg: float
    fill_fraction: float
    width: int
    height: int
    pixel_scale_arcsec: float
    estimated_memory_bytes: int
    products_by_component: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ViewportFitResult:
    canvas: dict[str, object]
    diagnostics: FramingDiagnostics
    warnings: tuple[str, ...]
    product_ids: tuple[str, ...]
    boundaries_deg: tuple[tuple[tuple[float, float], ...], ...]


def fit_fits_paths(
    paths: Iterable[str | Path], product_ids: Iterable[str] | None = None,
) -> ViewportFitResult:
    sources = [Path(path).resolve() for path in paths]
    identities = list(product_ids) if product_ids is not None else [path.name for path in sources]
    if len(sources) != len(identities):
        raise ValueError("FITS paths and product identities must have equal length")
    planes: list[FITSPlane] = []
    failures: list[str] = []
    for path, identity in zip(sources, identities):
        try:
            planes.append(load_fits_plane(path))
        except Exception as exc:
            failures.append(f"{identity}: {exc}")
    if failures:
        raise ValueError("unusable selected FITS footprints: " + "; ".join(failures))
    return fit_planes(planes, identities)


def fit_planes(planes: list[FITSPlane], product_ids: Iterable[str] | None = None) -> ViewportFitResult:
    if not planes:
        raise ValueError("at least one selected FITS plane is required for framing")
    identities = list(product_ids) if product_ids is not None else [plane.plane_id for plane in planes]
    if len(planes) != len(identities):
        raise ValueError("FITS planes and product identities must have equal length")

    sky_boundaries: list[SkyCoord] = []
    scales: list[float] = []
    failures: list[str] = []
    for plane, identity in zip(planes, identities):
        try:
            sky_boundaries.append(_sky_boundary(plane))
            celestial = plane.wcs.celestial
            values = np.abs(proj_plane_pixel_scales(celestial)) * 3600.0
            scales.extend(float(value) for value in values if np.isfinite(value) and value > 0)
        except Exception as exc:
            failures.append(f"{identity}: {exc}")
    if failures:
        raise ValueError("unusable selected FITS footprints: " + "; ".join(failures))
    if not scales:
        raise ValueError("selected FITS footprints have no finite positive celestial pixel scale")

    all_sky = SkyCoord(
        np.concatenate([boundary.icrs.ra.deg for boundary in sky_boundaries]) * u.deg,
        np.concatenate([boundary.icrs.dec.deg for boundary in sky_boundaries]) * u.deg,
        frame="icrs",
    )
    centroid_vector = np.zeros(3, dtype=float)
    total_area = 0.0
    for boundary in sky_boundaries:
        area, moment = _spherical_area_moment(boundary)
        centroid_vector += moment
        total_area += area
    if total_area <= 0:
        centroid_vector = np.mean(all_sky.cartesian.xyz.value, axis=1)
    norm = float(np.linalg.norm(centroid_vector))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("selected footprints do not admit a stable spherical tangent point")
    unit_vector = centroid_vector / norm
    centroid = SkyCoord(
        ra=math.degrees(math.atan2(unit_vector[1], unit_vector[0])) * u.deg,
        dec=math.degrees(math.asin(unit_vector[2])) * u.deg,
        frame="icrs",
    )
    projected = [_gnomonic_project(boundary, centroid) for boundary in sky_boundaries]
    combined = np.vstack(projected)
    hull = _convex_polygon(combined)
    angle, bounds = _minimum_area_rectangle(hull)
    min_u, max_u, min_v, max_v = bounds
    center_u = (min_u + max_u) / 2.0
    center_v = (min_v + max_v) / 2.0
    axis_u = np.array([math.cos(angle), math.sin(angle)])
    axis_v = np.array([-math.sin(angle), math.cos(angle)])
    center_xy = center_u * axis_u + center_v * axis_v
    center = _gnomonic_inverse(center_xy[0], center_xy[1], centroid)

    base_scale = min(scales)
    width_deg = max_u - min_u
    height_deg = max_v - min_v
    pad_u = max(width_deg * 0.02, 2.0 * base_scale / 3600.0)
    pad_v = max(height_deg * 0.02, 2.0 * base_scale / 3600.0)
    padded_width = width_deg + 2.0 * pad_u
    padded_height = height_deg + 2.0 * pad_v
    pixel_scale = max(
        base_scale,
        padded_width * 3600.0 / MAX_PREVIEW_DIMENSION,
        padded_height * 3600.0 / MAX_PREVIEW_DIMENSION,
    )
    width = max(1, math.ceil(padded_width * 3600.0 / pixel_scale) + 1)
    height = max(1, math.ceil(padded_height * 3600.0 / pixel_scale) + 1)
    width = min(width, MAX_PREVIEW_DIMENSION)
    height = min(height, MAX_PREVIEW_DIMENSION)
    rotation = (180.0 - math.degrees(angle)) % 180.0
    if math.isclose(rotation, 180.0, abs_tol=1e-10):
        rotation = 0.0
    canvas: dict[str, object] = {
        "center": {"mode": "explicit", "ra_deg": float(center.ra.deg), "dec_deg": float(center.dec.deg)},
        "projection": "TAN", "pixel_scale_arcsec": float(pixel_scale),
        "width": width, "height": height, "rotation_deg": rotation,
        "flux_conserving": True, "frame_origin": "selected_footprints",
    }
    canvas = _ensure_containment(canvas, all_sky)

    component_indices = _components(projected, base_scale / 3600.0)
    groups = tuple(tuple(identities[index] for index in group) for group in component_indices)
    span = _greatest_separation(all_sky)
    individual_areas = [_polygon_area(_convex_polygon(points)) for points in projected]
    union_area_estimate = min(sum(individual_areas), max(width_deg * height_deg, 0.0))
    fill = union_area_estimate / (width_deg * height_deg) if width_deg > 0 and height_deg > 0 else 1.0
    largest_diagonal = max(_polygon_diagonal(points) for points in projected)
    warning_reasons: list[str] = []
    if len(groups) > 1 and fill < 0.25:
        warning_reasons.append("disconnected footprints occupy less than 25% of the fitted frame")
    if len(groups) > 1 and span > 3.0 * largest_diagonal:
        warning_reasons.append("separation exceeds three times the largest component diagonal")
    if span > 5.0:
        warning_reasons.append("total angular span exceeds 5 degrees")
    diagnostics = FramingDiagnostics(
        component_count=len(groups), angular_span_deg=span,
        frame_width_deg=padded_width, frame_height_deg=padded_height,
        fill_fraction=float(min(max(fill, 0.0), 1.0)),
        width=int(canvas["width"]), height=int(canvas["height"]),
        pixel_scale_arcsec=float(canvas["pixel_scale_arcsec"]),
        estimated_memory_bytes=int(canvas["width"]) * int(canvas["height"]) * len(planes) * 64,
        products_by_component=groups,
    )
    warnings = tuple(_warning_text(reason, diagnostics) for reason in warning_reasons)
    boundaries = tuple(
        tuple((float(ra), float(dec)) for ra, dec in zip(boundary.icrs.ra.deg, boundary.icrs.dec.deg))
        for boundary in sky_boundaries
    )
    return ViewportFitResult(canvas, diagnostics, warnings, tuple(identities), boundaries)


def render_fit_preview(
    result: ViewportFitResult, maximum_dimension: int = 720,
) -> np.ndarray:
    """Rasterize selected sky boundaries in the exact proposed fitted canvas."""
    if maximum_dimension < 32:
        raise ValueError("fit preview maximum dimension must be at least 32 pixels")
    canvas_data = {
        key: value for key, value in result.canvas.items() if key != "frame_origin"
    }
    config = CanvasConfig.model_validate(canvas_data)
    center_data = result.canvas["center"]
    if not isinstance(center_data, dict):
        raise ValueError("fitted canvas requires an explicit center")
    center = SkyCoord(
        float(center_data["ra_deg"]) * u.deg,
        float(center_data["dec_deg"]) * u.deg,
        frame="icrs",
    )
    output_wcs, _ = build_output_wcs(config, center)
    full_width, full_height = config.width, config.height
    reduction = min(1.0, maximum_dimension / max(full_width, full_height))
    preview_width = max(2, int(round(full_width * reduction)))
    preview_height = max(2, int(round(full_height * reduction)))
    x_scale = (preview_width - 1) / max(full_width - 1, 1)
    y_scale = (preview_height - 1) / max(full_height - 1, 1)

    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (preview_width, preview_height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    colors = [
        (0, 220, 255), (255, 80, 210), (255, 215, 0), (80, 255, 120),
        (255, 120, 60), (160, 120, 255),
    ]
    for index, boundary in enumerate(result.boundaries_deg):
        sky = SkyCoord(
            [point[0] for point in boundary] * u.deg,
            [point[1] for point in boundary] * u.deg,
            frame="icrs",
        )
        x, y = output_wcs.world_to_pixel(sky)
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError(f"preview projection is nonfinite for {result.product_ids[index]}")
        points = [(float(px) * x_scale, float(py) * y_scale) for px, py in zip(x, y)]
        color = colors[index % len(colors)]
        draw.line([*points, points[0]], fill=(*color, 255), width=3, joint="curve")
    draw.rectangle(
        (0, 0, preview_width - 1, preview_height - 1),
        outline=(255, 255, 255, 255), width=2,
    )
    return np.asarray(image.convert("RGB"))


def _spherical_area_moment(boundary: SkyCoord) -> tuple[float, np.ndarray]:
    vectors = boundary.icrs.cartesian.xyz.value.T
    anchor = vectors[0]
    total = 0.0
    moment = np.zeros(3, dtype=float)
    for index in range(1, len(vectors) - 1):
        left, right = vectors[index], vectors[index + 1]
        denominator = 1.0 + np.dot(anchor, left) + np.dot(left, right) + np.dot(right, anchor)
        area = 2.0 * math.atan2(abs(float(np.dot(anchor, np.cross(left, right)))), denominator)
        triangle_center = anchor + left + right
        center_norm = float(np.linalg.norm(triangle_center))
        if area > 0 and center_norm > 0:
            total += area
            moment += area * triangle_center / center_norm
    return total, moment


def _sky_boundary(plane: FITSPlane) -> SkyCoord:
    data = np.asarray(plane.data)
    if data.ndim != 2:
        raise ValueError("science plane is not two-dimensional")
    valid = np.isfinite(data)
    if plane.mask is not None:
        valid &= ~np.asarray(plane.mask, dtype=bool)
    rows = np.flatnonzero(np.any(valid, axis=1))
    if not len(rows):
        raise ValueError("science plane has no valid pixels after masks")
    points: list[tuple[float, float]] = []
    for row in rows:
        columns = np.flatnonzero(valid[row])
        points.extend([
            (float(columns[0]) - 0.5, float(row) - 0.5),
            (float(columns[0]) - 0.5, float(row) + 0.5),
            (float(columns[-1]) + 0.5, float(row) - 0.5),
            (float(columns[-1]) + 0.5, float(row) + 0.5),
        ])
    pixels = _convex_polygon(np.asarray(points))
    ra, dec = plane.wcs.celestial.pixel_to_world_values(pixels[:, 0], pixels[:, 1])
    if not np.all(np.isfinite(ra)) or not np.all(np.isfinite(dec)):
        raise ValueError("valid-support boundary has nonfinite sky coordinates")
    return SkyCoord(ra=np.asarray(ra) * u.deg, dec=np.asarray(dec) * u.deg, frame="icrs")


def _gnomonic_project(points: SkyCoord, center: SkyCoord) -> np.ndarray:
    separation = center.separation(points).rad
    if np.any(~np.isfinite(separation)) or np.any(separation >= math.pi / 2):
        raise ValueError("selected footprints cannot share a finite TAN projection")
    position_angle = center.position_angle(points).rad
    radius = np.tan(separation)
    return np.column_stack((np.degrees(radius * np.sin(position_angle)),
                            np.degrees(radius * np.cos(position_angle))))


def _gnomonic_inverse(x_deg: float, y_deg: float, center: SkyCoord) -> SkyCoord:
    radius = math.hypot(math.radians(x_deg), math.radians(y_deg))
    separation = math.atan(radius)
    position_angle = math.atan2(x_deg, y_deg) * u.rad
    return center.directional_offset_by(position_angle, separation * u.rad).icrs


def _convex_polygon(points: np.ndarray) -> np.ndarray:
    unique = np.unique(np.asarray(points, dtype=float), axis=0)
    if len(unique) < 3:
        raise ValueError("valid-support boundary has fewer than three distinct points")
    return unique[ConvexHull(unique).vertices]


def _minimum_area_rectangle(hull: np.ndarray) -> tuple[float, tuple[float, float, float, float]]:
    edges = np.roll(hull, -1, axis=0) - hull
    angles = np.unique(np.mod(np.arctan2(edges[:, 1], edges[:, 0]), math.pi / 2.0))
    best: tuple[float, float, tuple[float, float, float, float]] | None = None
    for angle in angles:
        u_axis = np.array([math.cos(angle), math.sin(angle)])
        v_axis = np.array([-math.sin(angle), math.cos(angle)])
        u_values, v_values = hull @ u_axis, hull @ v_axis
        bounds = (float(u_values.min()), float(u_values.max()),
                  float(v_values.min()), float(v_values.max()))
        area = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
        candidate = (float(area), float(angle), bounds)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    return best[1], best[2]


def _ensure_containment(canvas: dict[str, object], points: SkyCoord) -> dict[str, object]:
    for _ in range(8):
        config = CanvasConfig.model_validate({key: value for key, value in canvas.items() if key != "frame_origin"})
        center_data = canvas["center"]
        assert isinstance(center_data, dict)
        center = SkyCoord(float(center_data["ra_deg"]) * u.deg, float(center_data["dec_deg"]) * u.deg)
        output_wcs, _ = build_output_wcs(config, center)
        x, y = output_wcs.world_to_pixel(points)
        if np.all(np.isfinite(x)) and np.all(x >= -0.5) and np.all(x <= int(canvas["width"]) - 0.5) \
                and np.all(y >= -0.5) and np.all(y <= int(canvas["height"]) - 0.5):
            return canvas
        canvas["width"] = min(int(canvas["width"]) + 2, MAX_PREVIEW_DIMENSION)
        canvas["height"] = min(int(canvas["height"]) + 2, MAX_PREVIEW_DIMENSION)
    raise ValueError("fitted TAN canvas could not be verified to contain every selected footprint")


def _components(polygons: list[np.ndarray], tolerance: float) -> list[list[int]]:
    groups: list[set[int]] = [{index} for index in range(len(polygons))]
    for left in range(len(polygons)):
        for right in range(left + 1, len(polygons)):
            if _polygon_distance(polygons[left], polygons[right]) <= tolerance:
                left_group = next(group for group in groups if left in group)
                right_group = next(group for group in groups if right in group)
                if left_group is not right_group:
                    left_group.update(right_group)
                    groups.remove(right_group)
    return [sorted(group) for group in groups]


def _polygon_distance(left: np.ndarray, right: np.ndarray) -> float:
    if _point_in_convex(left[0], right) or _point_in_convex(right[0], left):
        return 0.0
    for left_index in range(len(left)):
        for right_index in range(len(right)):
            if _segments_intersect(
                left[left_index], left[(left_index + 1) % len(left)],
                right[right_index], right[(right_index + 1) % len(right)],
            ):
                return 0.0
    distance = math.inf
    for first in (left, right):
        second = right if first is left else left
        for point in first:
            for index in range(len(second)):
                distance = min(distance, _point_segment_distance(
                    point, second[index], second[(index + 1) % len(second)]
                ))
    return distance


def _segments_intersect(
    first_start: np.ndarray, first_end: np.ndarray,
    second_start: np.ndarray, second_end: np.ndarray,
) -> bool:
    def cross(start: np.ndarray, end: np.ndarray, point: np.ndarray) -> float:
        delta = end - start
        offset = point - start
        return float(delta[0] * offset[1] - delta[1] * offset[0])

    first_left = cross(first_start, first_end, second_start)
    first_right = cross(first_start, first_end, second_end)
    second_left = cross(second_start, second_end, first_start)
    second_right = cross(second_start, second_end, first_end)
    return first_left * first_right <= 1e-18 and second_left * second_right <= 1e-18


def _point_in_convex(point: np.ndarray, polygon: np.ndarray) -> bool:
    edges = np.roll(polygon, -1, axis=0) - polygon
    offsets = point - polygon
    crosses = edges[:, 0] * offsets[:, 1] - edges[:, 1] * offsets[:, 0]
    return bool(np.all(crosses >= -1e-12) or np.all(crosses <= 1e-12))


def _point_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    delta = end - start
    if np.allclose(delta, 0):
        return float(np.linalg.norm(point - start))
    fraction = float(np.clip(np.dot(point - start, delta) / np.dot(delta, delta), 0.0, 1.0))
    return float(np.linalg.norm(point - (start + fraction * delta)))


def _polygon_area(polygon: np.ndarray) -> float:
    return abs(float(np.sum(polygon[:, 0] * np.roll(polygon[:, 1], -1)
                            - polygon[:, 1] * np.roll(polygon[:, 0], -1))) / 2.0)


def _polygon_diagonal(polygon: np.ndarray) -> float:
    return max(float(np.linalg.norm(left - right)) for left in polygon for right in polygon)


def _greatest_separation(points: SkyCoord) -> float:
    maximum = 0.0
    for index in range(len(points)):
        maximum = max(maximum, float(np.max(points[index].separation(points[index + 1:]).deg))
                      if index + 1 < len(points) else 0.0)
    return maximum


def _warning_text(reason: str, diagnostics: FramingDiagnostics) -> str:
    groups = "; ".join(", ".join(group) for group in diagnostics.products_by_component)
    return (
        f"Geometry is consistent with unrelated or widely separated scans: {reason}. "
        f"components={diagnostics.component_count}; span={diagnostics.angular_span_deg:.3f} deg; "
        f"frame={diagnostics.frame_width_deg:.3f} x {diagnostics.frame_height_deg:.3f} deg; "
        f"fill={diagnostics.fill_fraction:.3f}; raster={diagnostics.width}x{diagnostics.height}; "
        f"estimated memory={diagnostics.estimated_memory_bytes / (1024 ** 2):.1f} MiB; "
        f"products by component: {groups}"
    )

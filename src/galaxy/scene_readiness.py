"""Action-specific validation; no downloads, defaulting, or filesystem access."""
from __future__ import annotations

from collections.abc import Mapping as PlaneMap
from dataclasses import dataclass
from typing import Any, Literal

from .scene_models import SceneCard, document, effective_inputs


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    path: str
    message: str
    code: str = "incomplete"


Action = Literal["name_resolution", "discovery", "render", "export"]
Branch = Literal["original", "deconvolved"]


def readiness(
    card: SceneCard, action: Action, *, plane_filters: PlaneMap[str, str] | None = None,
    branch: Branch = "original", render_id: str | None = None,
) -> list[ReadinessIssue]:
    """Return field-addressed issues. Empty means ready, not binary availability."""
    card = SceneCard.model_validate(document(card))
    if action not in ("name_resolution", "discovery", "render", "export"):
        raise ValueError(f"unknown action: {action}")
    if branch not in ("original", "deconvolved"):
        raise ValueError(f"unknown branch: {branch}")
    if plane_filters is not None and any(not isinstance(k, str) or not k.strip()
                                         or not isinstance(v, str) or not v.strip()
                                         for k, v in plane_filters.items()):
        raise ValueError("plane_filters requires nonblank plane and filter identifiers")
    data = document(card)
    issues: list[ReadinessIssue] = []

    def need(path: str) -> Any:
        value: Any = data
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is None:
            issues.append(ReadinessIssue(path, "must be explicitly supplied"))
        return value

    def issue(path: str, message: str, code: str = "incomplete") -> None:
        issues.append(ReadinessIssue(path, message, code))

    if action == "name_resolution":
        target = data.get("target", {})
        if not (("ra_deg" in target and "dec_deg" in target) or ("ra" in target and "dec" in target)):
            need("target.name")
        return issues
    if action == "discovery":
        _discovery(data, need, issue)
        return issues
    if action == "export":
        need("output.format")
        need("output.destination_directory")
        candidates = [r for r in card.renders or [] if render_id is None or r.render_id == render_id]
        if not any(r.branch == branch and r.content_revision == card.content_revision
                   and effective_inputs(r.inputs) == effective_inputs(card) for r in candidates):
            issue("renders", "a successful render matching current inputs and requested branch is required", "stale")
        return issues

    for path in (
        "canvas.center.mode", "canvas.center.ra_deg", "canvas.center.dec_deg",
        "canvas.projection", "canvas.pixel_scale_arcsec", "canvas.width", "canvas.height",
        "canvas.rotation_deg", "canvas.flux_conserving", "planes.enabled_filters",
        "planes.disabled_plane_ids", "planes.export_multiplane_fits", "psf.enabled",
        "tone.percentiles.black", "tone.percentiles.white", "tone.saturation",
    ):
        need(path)
    for channel in ("red", "green", "blue"):
        for path in (f"tone.stretch.{channel}.kind", f"tone.stretch.{channel}.parameter",
                     f"tone.gain.{channel}", f"tone.bias.{channel}"):
            need(path)
    if data.get("canvas", {}).get("center", {}).get("mode") != "explicit":
        issue("canvas.center.mode", "render requires an explicit resolved center")

    selection = data.get("selection", {})
    products = {p["product_id"]: p for p in selection.get("products", [])}
    selected = selection.get("selected_product_ids", [])
    if not selected:
        issue("selection.selected_product_ids", "select at least one exact product")
    for pid in selected:
        if pid not in products:
            issue("selection.selected_product_ids", f"unknown product: {pid}", "reference")
    assets = data.get("assets", {})
    for pid in selected:
        product = products.get(pid, {})
        aid = product.get("cached_asset_id")
        if aid and assets.get(aid, {}).get("kind") != "source":
            issue("selection.products", f"{pid}: cached asset must reference a source", "reference")
    enabled_filters = set(data.get("planes", {}).get("enabled_filters", []))
    disabled = set(data.get("planes", {}).get("disabled_plane_ids", []))
    if not enabled_filters:
        issue("planes.enabled_filters", "enable at least one filter")

    if plane_filters is None:
        issue("planes", "inspected plane-to-filter associations are required", "inspection_required")
        return issues
    source = dict(plane_filters)
    if not source:
        issue("planes", "no usable source planes were inspected")
    product_filters = {products[pid].get("filter") for pid in selected if pid in products}
    if any(value not in product_filters for value in source.values()):
        issue("selection.products", "inspected filters must belong to selected product metadata", "reference")
    for filt in enabled_filters - set(source.values()):
        issue("planes.enabled_filters", f"unresolved filter: {filt}", "reference")
    known = set(source)
    enabled = {pid for pid, filt in source.items() if filt in enabled_filters and pid not in disabled}
    mapping = data.get("mapping", {})
    for index, derived in enumerate(mapping.get("derived_planes", [])):
        path = f"mapping.derived_planes.{index}"
        name = derived["name"]
        if name in known:
            issue(path + ".name", "derived name collides with an existing plane", "reference")
        operand_fields = ("terms",) if derived["operation"] == "linear_combination" else ("numerator", "denominator")
        refs: list[str] = []
        for field in operand_fields:
            terms = derived.get(field, [])
            if not terms:
                issue(path + "." + field, "requires at least one term")
            refs.extend(t["plane"] for t in terms)
        if derived["operation"] == "ratio" and "epsilon" not in derived:
            issue(path + ".epsilon", "must be explicitly supplied")
        for ref in refs:
            if ref not in known:
                issue(path, f"unresolved or forward/cyclic plane reference: {ref}", "reference")
        known.add(name)
        if refs and all(ref in enabled for ref in refs) and name not in disabled:
            enabled.add(name)
    for pid in disabled - known:
        issue("planes.disabled_plane_ids", f"unknown plane: {pid}", "reference")

    by_plane: dict[str, dict[str, Any]] = {}
    by_filter: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(mapping.get("planes", [])):
        path = f"mapping.planes.{index}"
        if "plane" not in entry and "filter" not in entry:
            issue(path, "requires exactly one plane or filter selector")
        if "plane" in entry:
            if entry["plane"] not in known:
                issue(path + ".plane", "unknown plane", "reference")
            by_plane[entry["plane"]] = entry.get("rgb", {})
        if "filter" in entry:
            if entry["filter"] not in source.values():
                issue(path + ".filter", "unknown filter", "reference")
            by_filter[entry["filter"]] = entry.get("rgb", {})
        for channel in ("red", "green", "blue"):
            if channel not in entry.get("rgb", {}):
                issue(path + ".rgb." + channel, "must be explicitly supplied")
    nonzero = False
    for pid in sorted(enabled):
        rgb = by_plane.get(pid, by_filter.get(source.get(pid, ""), {}))
        if not all(c in rgb for c in ("red", "green", "blue")):
            issue("mapping.planes", f"concrete RGB contribution required for enabled plane: {pid}")
        elif any(rgb[c] != 0 for c in ("red", "green", "blue")):
            nonzero = True
    if not nonzero:
        issue("mapping.planes", "at least one enabled plane must contribute a nonzero weight")

    psf = data.get("psf", {})
    policies = psf.get("per_plane", {})
    for pid in policies:
        if pid not in source:
            issue("psf.per_plane", f"unknown source plane: {pid}", "reference")
    if branch == "deconvolved":
        if psf.get("enabled") is not True:
            issue("psf.enabled", "deconvolved branch requires enabled PSF processing")
        applicable = enabled & set(source)
        processed = False
        for pid in sorted(applicable):
            policy = policies.get(pid, {})
            if "enabled" not in policy:
                issue(f"psf.per_plane.{pid}.enabled", "explicit per-plane policy required")
            if policy.get("enabled"):
                processed = True
                for key in ("kernel_asset_id", "max_iterations", "regularization"):
                    if key not in policy:
                        issue(f"psf.per_plane.{pid}.{key}", "must be explicitly supplied")
                if assets.get(policy.get("kernel_asset_id"), {}).get("kind") != "psf_kernel":
                    issue(f"psf.per_plane.{pid}.kernel_asset_id", "requires a PSF kernel asset", "reference")
        if not processed:
            issue("psf.per_plane", "enable processing for at least one active source plane")
    return issues


def _discovery(data: dict[str, Any], need: Any, issue: Any) -> None:
    target = data.get("target", {})
    decimal = ("ra_deg" in target, "dec_deg" in target)
    sexagesimal = ("ra" in target, "dec" in target)
    if any(decimal) and not all(decimal):
        issue("target", "decimal coordinates require both RA and Dec")
    if any(sexagesimal) and not all(sexagesimal):
        issue("target", "sexagesimal coordinates require both RA and Dec")
    sex = None
    if all(sexagesimal):
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        try:
            sex = SkyCoord(target["ra"], target["dec"], unit=(u.hourangle, u.deg), frame="icrs")
        except (ValueError, TypeError) as exc:
            issue("target", f"invalid sexagesimal coordinates: {exc}", "invalid")
    if not all(decimal) and sex is None:
        issue("target", "resolve coordinates before searching MAST")
    if all(decimal) and sex is not None:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        dec = SkyCoord(target["ra_deg"], target["dec_deg"], unit=u.deg, frame="icrs")
        if dec.separation(sex).arcsec > 1e-6:
            issue("target", "decimal and sexagesimal coordinates conflict", "conflict")
    need("target.coordinate_frame")
    kind = need("target.region.kind")
    if kind == "circle":
        need("target.region.radius_arcmin")
    if kind == "box":
        need("target.region.width_arcmin")
        need("target.region.height_arcmin")
    need("search.observation_selection")


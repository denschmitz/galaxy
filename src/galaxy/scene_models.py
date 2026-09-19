"""Revision-one JSON scene cards. Draft completeness is checked separately."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, model_validator


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def timestamp(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
        raise ValueError("must be a UTC RFC3339 timestamp ending Z")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def relative_path(value: str) -> str:
    path = PureWindowsPath(value)
    if path.drive or path.root or ".." in path.parts or ":" in value or not path.parts:
        raise ValueError("asset path must be relative and cannot escape the card directory")
    return value


def http_url(value: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("requires an HTTP(S) URL")
    return value


Text = Annotated[str, Field(pattern=r".*\S.*"), AfterValidator(nonblank)]
UTC = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"), AfterValidator(timestamp)]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
RA = Annotated[float, Field(ge=0, lt=360)]
DEC = Annotated[float, Field(ge=-90, le=90)]
URL = Annotated[Text, AfterValidator(http_url)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if item is None:
                    raise ValueError(f"{key}: omit unknown values instead of null")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema)
        for field in schema.get("properties", {}).values():
            if "anyOf" in field:
                choices = [item for item in field["anyOf"] if item != {"type": "null"}]
                if len(choices) == 1:
                    field.pop("anyOf")
                    field.update(choices[0])
                else:
                    field["anyOf"] = choices
            if field.get("default", ...) is None:
                field.pop("default")
        return schema


class Region(Model):
    kind: Literal["circle", "box"] | None = None
    radius_arcmin: Positive | None = None
    width_arcmin: Positive | None = None
    height_arcmin: Positive | None = None

    @model_validator(mode="after")
    def dimensions(self) -> Region:
        if self.kind == "circle" and (self.width_arcmin is not None or self.height_arcmin is not None):
            raise ValueError("circle does not accept box dimensions")
        if self.kind == "box" and self.radius_arcmin is not None:
            raise ValueError("box does not accept radius")
        return self


class Target(Model):
    name: Text | None = None
    resolved_name: Text | None = None
    ra_deg: RA | None = None
    dec_deg: DEC | None = None
    ra: Text | None = None
    dec: Text | None = None
    coordinate_frame: Literal["ICRS"] | None = None
    region: Region | None = None


class Search(Model):
    missions: list[Text] | None = None
    instruments: list[Text] | None = None
    detectors: list[Text] | None = None
    filters: list[Text] | None = None
    product_types: list[Text] | None = None
    observation_date_start: UTC | None = None
    observation_date_end: UTC | None = None
    observation_selection: Literal["all", "latest_per_filter", "deepest_per_filter"] | None = None
    max_observations_per_filter: PositiveInt | None = None
    max_total_observations: PositiveInt | None = None

    @model_validator(mode="after")
    def dates(self) -> Search:
        if self.observation_date_start and self.observation_date_end:
            if datetime.fromisoformat(self.observation_date_start) > datetime.fromisoformat(self.observation_date_end):
                raise ValueError("observation_date_start must not follow observation_date_end")
        return self


class Source(Model):
    source_kind: Literal["release_tracker", "name_resolver"]
    source_url: URL
    retrieved_at: UTC
    extracted_metadata: dict[str, JsonValue]


class Discovery(Model):
    sources: list[Source] | None = None
    candidate_manifest_asset_id: Text | None = None
    archive_retrieved_at: UTC | None = None


class Product(Model):
    product_id: Text
    archive: Literal["MAST"] | None = None
    data_uri: Text | None = None
    observation_id: Text | None = None
    mission: Text | None = None
    instrument: Text | None = None
    detector: Text | None = None
    filter: Text | None = None
    product_type: Text | None = None
    product_version: Text | None = None
    filename: Text | None = None
    exposure_seconds: Nonnegative | None = None
    observed_at: UTC | None = None
    cached_asset_id: Text | None = None


def unique(values: list[str], path: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{path}: duplicate identifiers")


class Selection(Model):
    products: list[Product] | None = None
    selected_product_ids: list[Text] | None = None
    observation_ids: list[Text] | None = None

    @model_validator(mode="after")
    def identifiers(self) -> Selection:
        unique([p.product_id for p in self.products or []], "products")
        unique(self.selected_product_ids or [], "selected_product_ids")
        unique(self.observation_ids or [], "observation_ids")
        return self


class Center(Model):
    mode: Literal["explicit", "resolved_target"] | None = None
    ra_deg: RA | None = None
    dec_deg: DEC | None = None

    @model_validator(mode="after")
    def coordinate_mode(self) -> Center:
        if self.mode == "resolved_target" and (self.ra_deg is not None or self.dec_deg is not None):
            raise ValueError("resolved_target center does not accept explicit coordinates")
        return self


class ViewState(Model):
    zoom: Positive | None = None
    pan_x: float | None = None
    pan_y: float | None = None


class Canvas(Model):
    center: Center | None = None
    projection: Literal["TAN"] | None = None
    pixel_scale_arcsec: Positive | None = None
    width: PositiveInt | None = None
    height: PositiveInt | None = None
    rotation_deg: RA | None = None
    flux_conserving: bool | None = None
    view_state: ViewState | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_rotation(cls, data: Any) -> Any:
        if isinstance(data, dict) and type(data.get("rotation_deg")) in (int, float) and data["rotation_deg"] == 360:
            return {**data, "rotation_deg": 0.0}
        return data


class Planes(Model):
    enabled_filters: list[Text] | None = None
    disabled_plane_ids: list[Text] | None = None
    export_multiplane_fits: bool | None = None

    @model_validator(mode="after")
    def identifiers(self) -> Planes:
        unique(self.enabled_filters or [], "enabled_filters")
        unique(self.disabled_plane_ids or [], "disabled_plane_ids")
        return self


class RGB(Model):
    red: float | None = None
    green: float | None = None
    blue: float | None = None


class Contribution(Model):
    plane: Text | None = None
    filter: Text | None = None
    label: Text | None = None
    rgb: RGB | None = None

    @model_validator(mode="after")
    def selector(self) -> Contribution:
        if self.plane is not None and self.filter is not None:
            raise ValueError("specify exactly one of plane or filter")
        return self


class Term(Model):
    plane: Text
    weight: float


class DerivedPlane(Model):
    name: Text
    operation: Literal["linear_combination", "ratio"]
    terms: list[Term] | None = None
    numerator: list[Term] | None = None
    denominator: list[Term] | None = None
    epsilon: Positive | None = None


class MappingDefaults(Model):
    strategy: Literal["continuum", "wavelength_order"] | None = None


class Mapping(Model):
    defaults: MappingDefaults | None = None
    planes: list[Contribution] | None = None
    derived_planes: list[DerivedPlane] | None = None

    @model_validator(mode="after")
    def selectors(self) -> Mapping:
        selectors = [f"plane:{p.plane}" if p.plane else f"filter:{p.filter}"
                     for p in self.planes or [] if p.plane or p.filter]
        unique(selectors, "mapping.planes")
        unique([p.name for p in self.derived_planes or []], "derived_planes")
        return self


class Stretch(Model):
    kind: Literal["asinh", "gamma"] | None = None
    parameter: Positive | None = None


class Stretches(Model):
    red: Stretch | None = None
    green: Stretch | None = None
    blue: Stretch | None = None


class Percentiles(Model):
    black: Annotated[float, Field(ge=0, le=100)] | None = None
    white: Annotated[float, Field(ge=0, le=100)] | None = None

    @model_validator(mode="after")
    def order(self) -> Percentiles:
        if self.black is not None and self.white is not None and self.black >= self.white:
            raise ValueError("black must be lower than white")
        return self


class Tone(Model):
    stretch: Stretches | None = None
    percentiles: Percentiles | None = None
    gain: RGB | None = None
    bias: RGB | None = None
    saturation: Nonnegative | None = None


class PSFPlane(Model):
    enabled: bool | None = None
    kernel_asset_id: Text | None = None
    max_iterations: Annotated[int, Field(ge=1, le=100)] | None = None
    regularization: Nonnegative | None = None


class PSF(Model):
    enabled: bool | None = None
    common_psf_fwhm_arcsec: Positive | None = None
    per_plane: dict[Text, PSFPlane] | None = None


class Execution(Model):
    fail_fast: bool | None = None
    log_file: Text | None = None
    debug_to_console: bool | None = None
    debug_to_file: bool | None = None


class Asset(Model):
    kind: Literal["source", "discovery_thumbnail", "render_image", "render_thumbnail",
                  "export_image", "aligned_planes", "footprint", "candidate_manifest",
                  "provenance", "psf_kernel"]
    path: Annotated[Text, AfterValidator(relative_path)] | None = None
    uri: Text | None = None
    media_type: Text | None = None
    byte_count: Annotated[int, Field(ge=0)] | None = None
    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")] | None = None
    source_url: URL | None = None
    credit: str | None = None

    @model_validator(mode="after")
    def location(self) -> Asset:
        if (self.path is None) == (self.uri is None):
            raise ValueError("asset requires exactly one of path or uri")
        if self.uri and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:\S+$", self.uri):
            raise ValueError("asset uri requires a scheme and locator")
        if self.kind == "discovery_thumbnail" and not self.source_url:
            raise ValueError("discovery thumbnail requires source_url")
        return self


class Inputs(Model):
    target: Target | None = None
    search: Search | None = None
    selection: Selection
    canvas: Canvas
    planes: Planes
    mapping: Mapping
    tone: Tone
    psf: PSF

    @model_validator(mode="after")
    def complete_snapshot(self) -> Inputs:
        data = document(self)
        paths = [
            "selection.products", "selection.selected_product_ids",
            "canvas.center.mode", "canvas.center.ra_deg", "canvas.center.dec_deg",
            "canvas.projection", "canvas.pixel_scale_arcsec", "canvas.width", "canvas.height",
            "canvas.rotation_deg", "canvas.flux_conserving", "planes.enabled_filters",
            "planes.disabled_plane_ids", "planes.export_multiplane_fits",
            "mapping.planes", "tone.percentiles.black", "tone.percentiles.white",
            "tone.saturation", "psf.enabled",
        ]
        for channel in ("red", "green", "blue"):
            paths.extend([f"tone.stretch.{channel}.kind", f"tone.stretch.{channel}.parameter",
                          f"tone.gain.{channel}", f"tone.bias.{channel}"])
        for path in paths:
            value: Any = data
            for key in path.split("."):
                value = value.get(key) if isinstance(value, dict) else None
            if value is None:
                raise ValueError(f"inputs.{path}: successful history requires complete inputs")
        if self.canvas.center is None or self.canvas.center.mode != "explicit":
            raise ValueError("inputs.canvas.center must be explicit")
        products = {p.product_id for p in self.selection.products or []}
        selected = self.selection.selected_product_ids or []
        if not selected or not set(selected) <= products:
            raise ValueError("inputs.selection requires nonempty resolved product references")
        if not self.planes.enabled_filters:
            raise ValueError("inputs.planes requires enabled filters")
        if not self.mapping.planes:
            raise ValueError("inputs.mapping requires concrete contributions")
        for entry in self.mapping.planes:
            if not (entry.plane or entry.filter) or entry.rgb is None or any(
                getattr(entry.rgb, c) is None for c in ("red", "green", "blue")
            ):
                raise ValueError("inputs.mapping requires complete selectors and RGB")
        if not any(any(getattr(entry.rgb, channel) != 0 for channel in ("red", "green", "blue"))
                   for entry in self.mapping.planes):
            raise ValueError("inputs.mapping requires a nonzero contribution")
        return self


class Render(Model):
    render_id: Text
    created_at: UTC
    content_revision: PositiveInt
    branch: Literal["original", "deconvolved"]
    image_asset_id: Text
    inputs: Inputs
    provenance_asset_id: Text
    thumbnail_asset_id: Text | None = None
    aligned_plane_asset_ids: list[Text] | None = None
    footprint_asset_id: Text | None = None

    @model_validator(mode="after")
    def processed_branch(self) -> Render:
        if self.branch == "deconvolved":
            policies = self.inputs.psf.per_plane or {}
            enabled = [policy for policy in policies.values() if policy.enabled]
            if self.inputs.psf.enabled is not True or not enabled:
                raise ValueError("deconvolved history requires enabled PSF processing")
            if any(policy.kernel_asset_id is None or policy.max_iterations is None
                   or policy.regularization is None for policy in enabled):
                raise ValueError("deconvolved history requires complete kernel policies")
        return self


class Output(Model):
    format: Literal["png", "tiff"] | None = None
    destination_directory: Text | None = None


class Export(Model):
    export_id: Text
    render_id: Text
    created_at: UTC
    format: Literal["png", "tiff"]
    destination: Text
    asset_id: Text | None = None


class SceneCard(Model):
    document_type: Literal["galaxy.scene_card"]
    schema_version: Literal[1]
    scene_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
    title: Text
    created_at: UTC
    updated_at: UTC
    content_revision: PositiveInt
    description: str | None = None
    target: Target | None = None
    search: Search | None = None
    discovery: Discovery | None = None
    selection: Selection | None = None
    canvas: Canvas | None = None
    planes: Planes | None = None
    mapping: Mapping | None = None
    tone: Tone | None = None
    psf: PSF | None = None
    execution: Execution | None = None
    assets: dict[Text, Asset] | None = None
    thumbnail_asset_id: Text | None = None
    renders: list[Render] | None = None
    exports: list[Export] | None = None
    output: Output | None = None

    @model_validator(mode="before")
    @classmethod
    def version_type(cls, value: Any) -> Any:
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def consistency(self) -> SceneCard:
        if str(UUID(self.scene_id)) != self.scene_id:
            raise ValueError("scene_id must be a canonical lowercase UUID")
        if datetime.fromisoformat(self.updated_at) < datetime.fromisoformat(self.created_at):
            raise ValueError("updated_at cannot precede created_at")
        unique([r.render_id for r in self.renders or []], "renders")
        unique([e.export_id for e in self.exports or []], "exports")
        assets = self.assets or {}
        revisions: dict[int, dict[str, Any]] = {self.content_revision: effective_inputs(self)}

        def reference(asset_id: str | None, kinds: tuple[str, ...], path: str) -> None:
            if asset_id is not None and (asset_id not in assets or assets[asset_id].kind not in kinds):
                raise ValueError(f"{path}: unresolved asset or wrong asset kind: {asset_id}")

        for render in self.renders or []:
            if render.content_revision > self.content_revision:
                raise ValueError("renders.content_revision cannot exceed current revision")
            snapshot = effective_inputs(render.inputs)
            if render.content_revision in revisions and revisions[render.content_revision] != snapshot:
                raise ValueError("renders.inputs: one revision cannot identify different inputs")
            revisions[render.content_revision] = snapshot
            reference(render.image_asset_id, ("render_image",), "renders.image_asset_id")
            reference(render.provenance_asset_id, ("provenance",), "renders.provenance_asset_id")
            reference(render.thumbnail_asset_id, ("render_thumbnail",), "renders.thumbnail_asset_id")
            reference(render.footprint_asset_id, ("footprint",), "renders.footprint_asset_id")
            for aid in render.aligned_plane_asset_ids or []:
                reference(aid, ("aligned_planes",), "renders.aligned_plane_asset_ids")
            for product in render.inputs.selection.products or []:
                reference(product.cached_asset_id, ("source",), "renders.inputs.selection")
            for policy in (render.inputs.psf.per_plane or {}).values():
                reference(policy.kernel_asset_id, ("psf_kernel",), "renders.inputs.psf")
        render_ids = {r.render_id for r in self.renders or []}
        for export in self.exports or []:
            if export.render_id not in render_ids:
                raise ValueError("exports.render_id: unknown render")
            reference(export.asset_id, ("export_image",), "exports.asset_id")
        reference(self.thumbnail_asset_id, ("discovery_thumbnail", "render_thumbnail"), "thumbnail_asset_id")
        if self.thumbnail_asset_id and assets[self.thumbnail_asset_id].kind == "render_thumbnail":
            if not any(r.thumbnail_asset_id == self.thumbnail_asset_id
                       and r.content_revision == self.content_revision
                       and effective_inputs(r.inputs) == effective_inputs(self)
                       for r in self.renders or []):
                raise ValueError("thumbnail_asset_id: generated thumbnail does not match current inputs")
        return self


INPUT_FIELDS = ("target", "search", "selection", "canvas", "planes", "mapping", "tone", "psf")


def document(model: Model) -> dict[str, Any]:
    """Preserve explicit empty collections and omitted draft fields."""
    return model.model_dump(mode="json", exclude_unset=True)


def effective_inputs(model: SceneCard | Inputs) -> dict[str, Any]:
    data = document(model)
    result = {key: data[key] for key in INPUT_FIELDS if key in data}
    if "canvas" in result:
        result["canvas"].pop("view_state", None)
    return result

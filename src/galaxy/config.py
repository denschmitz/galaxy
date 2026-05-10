from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


PROJECT_FORMAT_REVISION = 1
logger = logging.getLogger(__name__)


class GalaxyProjectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class GalaxyProjectValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("\n".join(_format_issue(issue) for issue in issues))


class CircleRegion(GalaxyProjectModel):
    kind: Literal["circle"]
    radius_arcmin: float = Field(gt=0)


class BoxRegion(GalaxyProjectModel):
    kind: Literal["box"]
    width_arcmin: float = Field(gt=0)
    height_arcmin: float = Field(gt=0)


class PolygonRegion(GalaxyProjectModel):
    kind: Literal["polygon"]
    vertices: list[tuple[float, float]] = Field(min_length=3)


RegionDefinition = CircleRegion | BoxRegion | PolygonRegion


class TargetConfig(GalaxyProjectModel):
    name: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    ra: str | None = None
    dec: str | None = None
    region: RegionDefinition

    @model_validator(mode="after")
    def validate_target(self) -> "TargetConfig":
        if self.ra_deg is not None or self.dec_deg is not None:
            if self.ra_deg is None or self.dec_deg is None:
                raise ValueError("target.ra_deg and target.dec_deg must be provided together")
            return self
        if self.ra or self.dec:
            if not (self.ra and self.dec):
                raise ValueError("target.ra and target.dec must be provided together")
            return self
        if self.name:
            return self
        raise ValueError("target must specify either name, decimal coordinates, or sexagesimal coordinates")


class SourceProductConfig(GalaxyProjectModel):
    stable_product_identifier: str
    product_filename: str | None = None
    data_uri: str | None = None
    obs_id: str | None = None
    obsid: str | None = None
    mission: str | None = None
    instrument: str | None = None
    detector: str | None = None
    filter: str | None = None
    product_type: str | None = None
    product_version: str | None = None


class SearchConfig(GalaxyProjectModel):
    missions: list[str] = Field(default_factory=lambda: ["HST", "JWST"])
    instruments: list[str] = Field(default_factory=list)
    detectors: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=lambda: ["SCIENCE", "DRZ", "DRC", "I2D"])
    observation_date_start: str | None = None
    observation_date_end: str | None = None
    observation_selection: Literal["all", "latest_per_filter", "deepest_per_filter"] = "all"
    max_observations_per_filter: int = Field(default=1, ge=1)
    max_total_observations: int | None = Field(default=None, ge=1)
    source_products: list[SourceProductConfig] = Field(default_factory=list)


class CanvasCenterResolvedTarget(GalaxyProjectModel):
    mode: Literal["resolved_target"]


class CanvasCenterExplicit(GalaxyProjectModel):
    mode: Literal["explicit"]
    ra_deg: float
    dec_deg: float


CanvasCenter = CanvasCenterResolvedTarget | CanvasCenterExplicit


class ViewStateConfig(GalaxyProjectModel):
    zoom: float | None = Field(default=None, gt=0)
    pan_x: float | None = None
    pan_y: float | None = None


class CanvasConfig(GalaxyProjectModel):
    center: CanvasCenter
    projection: str = "TAN"
    pixel_scale_arcsec: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation_deg: float = 0.0
    flux_conserving: bool = True
    view_state: ViewStateConfig | None = None


class PlanesConfig(GalaxyProjectModel):
    enabled_filters: list[str] = Field(default_factory=list)
    disabled_plane_ids: list[str] = Field(default_factory=list)
    export_multiplane_fits: bool = True


class PlaneContributionConfig(GalaxyProjectModel):
    plane: str
    weight: float = 1.0


class RGBMixConfig(GalaxyProjectModel):
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0


class PlaneMappingConfig(GalaxyProjectModel):
    plane: str | None = None
    filter: str | None = None
    label: str | None = None
    rgb: RGBMixConfig = Field(default_factory=RGBMixConfig)

    @model_validator(mode="after")
    def validate_selector(self) -> "PlaneMappingConfig":
        if self.plane or self.filter:
            return self
        raise ValueError("plane mapping entries must specify either plane or filter")


class DerivedPlaneConfig(GalaxyProjectModel):
    name: str
    operation: Literal["linear_combination", "ratio"]
    terms: list[PlaneContributionConfig] = Field(default_factory=list)
    numerator: list[PlaneContributionConfig] = Field(default_factory=list)
    denominator: list[PlaneContributionConfig] = Field(default_factory=list)
    epsilon: float = 1e-6

    @model_validator(mode="after")
    def validate_operands(self) -> "DerivedPlaneConfig":
        if self.operation == "linear_combination" and not self.terms:
            raise ValueError("linear_combination derived planes require terms")
        if self.operation == "ratio" and (not self.numerator or not self.denominator):
            raise ValueError("ratio derived planes require numerator and denominator terms")
        return self


class MappingDefaults(GalaxyProjectModel):
    strategy: Literal["continuum", "wavelength_order"] = "continuum"


class MappingConfig(GalaxyProjectModel):
    defaults: MappingDefaults = Field(default_factory=MappingDefaults)
    planes: list[PlaneMappingConfig] = Field(default_factory=list)
    derived_planes: list[DerivedPlaneConfig] = Field(default_factory=list)


class StretchConfig(GalaxyProjectModel):
    kind: Literal["asinh", "gamma"] = "asinh"
    parameter: float = Field(gt=0)


class ToneStretchSet(GalaxyProjectModel):
    red: StretchConfig
    green: StretchConfig
    blue: StretchConfig


class TonePercentiles(GalaxyProjectModel):
    black: float = Field(ge=0, le=100)
    white: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> "TonePercentiles":
        if self.black >= self.white:
            raise ValueError("tone.percentiles.black must be lower than tone.percentiles.white")
        return self


class ToneGainBias(GalaxyProjectModel):
    red: float = 1.0
    green: float = 1.0
    blue: float = 1.0


class ToneConfig(GalaxyProjectModel):
    stretch: ToneStretchSet
    percentiles: TonePercentiles
    gain: ToneGainBias = Field(default_factory=ToneGainBias)
    bias: ToneGainBias = Field(default_factory=lambda: ToneGainBias(red=0.0, green=0.0, blue=0.0))
    saturation: float = Field(default=1.0, ge=0)


class PSFPlaneConfig(GalaxyProjectModel):
    enabled: bool = False
    kernel_path: str | None = None
    max_iterations: int = Field(default=10, ge=1, le=100)
    regularization: float = Field(default=0.0, ge=0.0)


class PSFConfig(GalaxyProjectModel):
    enabled: bool = False
    common_psf_fwhm_arcsec: float | None = Field(default=None, gt=0)
    per_plane: dict[str, PSFPlaneConfig] = Field(default_factory=dict)


class ExecutionConfig(GalaxyProjectModel):
    fail_fast: bool = False
    log_file: str = "galaxy.log"
    debug_to_console: bool = False
    debug_to_file: bool = True


class GalaxyConfig(GalaxyProjectModel):
    format_revision: int = PROJECT_FORMAT_REVISION
    target: TargetConfig | None = None
    search: SearchConfig = Field(default_factory=SearchConfig)
    canvas: CanvasConfig
    planes: PlanesConfig = Field(default_factory=PlanesConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    tone: ToneConfig
    psf: PSFConfig = Field(default_factory=PSFConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    @model_validator(mode="after")
    def validate_project_structure(self) -> "GalaxyConfig":
        if self.format_revision != PROJECT_FORMAT_REVISION:
            raise ValueError(
                f"unsupported format revision {self.format_revision}; expected {PROJECT_FORMAT_REVISION}"
            )

        has_search_constraints = self.target is not None
        has_pinned_sources = bool(self.search.source_products)
        if not has_search_constraints and not has_pinned_sources:
            raise ValueError(
                "project must define either a search-driven scene (target plus search constraints) or pinned source_products"
            )
        if has_pinned_sources and self.target is None and self.canvas.center.mode != "explicit":
            raise ValueError("pinned source_products require either target metadata or an explicit canvas center")
        return self

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json", exclude_none=True), sort_keys=False)


def load_config(path: str | Path) -> GalaxyConfig:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    config, issues = validate_config_document(data)
    if config is None:
        for issue in issues:
            severity = logging.ERROR if issue.code in {"unknown_field", "unsupported_format_revision", "unsupported_section_combination"} else logging.ERROR
            logger.log(severity, "Project file validation failed at %s [%s]: %s", issue.path, issue.code, issue.message)
        raise GalaxyProjectValidationError(issues)
    return config


def dump_config(config: GalaxyConfig, path: str | Path) -> None:
    Path(path).write_text(config.to_yaml(), encoding="utf-8")


def validate_config_dict(data: dict[str, Any]) -> tuple[GalaxyConfig | None, list[str]]:
    config, issues = validate_config_document(data)
    return config, [_format_issue(issue) for issue in issues]


def validate_config_document(data: Any) -> tuple[GalaxyConfig | None, list[ValidationIssue]]:
    if not isinstance(data, dict):
        return None, [ValidationIssue(code="schema", path="<root>", message="project document must contain a mapping at the top level")]
    try:
        return GalaxyConfig.model_validate(data), []
    except ValidationError as exc:
        return None, _build_validation_issues(exc)


def _build_validation_issues(exc: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"]) or "<root>"
        code = str(error.get("type") or "schema")
        message = str(error["msg"])
        if code == "extra_forbidden":
            code = "unknown_field"
        elif "unsupported format revision" in message:
            code = "unsupported_format_revision"
        elif "pinned source_products" in message or "project must define either" in message:
            code = "unsupported_section_combination"
        issues.append(ValidationIssue(code=code, path=path, message=message))
    return issues


def _format_issue(issue: ValidationIssue) -> str:
    return f"{issue.path}: [{issue.code}] {issue.message}"

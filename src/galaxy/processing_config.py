from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator


PROJECT_FORMAT_REVISION = 1

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


class CoverageConfig(GalaxyProjectModel):
    policy: Literal["available_contributors", "common_required_bands"] = "available_contributors"
    tone_reference: Literal["output_support", "common_required_bands"] = "output_support"
    crop: Literal["none", "bounding_box"] = "none"
    padding_pixels: int = Field(default=0, ge=0)


class PlaneContributionConfig(GalaxyProjectModel):
    plane: str
    weight: float = 1.0


class RGBMixConfig(GalaxyProjectModel):
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0


class NormalizationReferenceConfig(GalaxyProjectModel):
    reference_id: str
    kind: Literal["region"] = "region"
    region_ids: list[str] = Field(min_length=1)
    branch: Literal["original", "deconvolved"]
    grid_id: str
    source_ids: list[str] = Field(min_length=1)
    unit: str | None = None
    coverage_policy: Literal["available_contributors", "common_required_bands"]
    tone_reference_policy: Literal["output_support", "common_required_bands"] = "output_support"
    black_percentile: float = Field(ge=0, le=100)
    white_percentile: float = Field(ge=0, le=100)
    black_value: float
    white_value: float
    sample_count: int = Field(ge=1)
    low_clipping_fraction: float = Field(ge=0, le=1)
    high_clipping_fraction: float = Field(ge=0, le=1)
    locked: Literal[True] = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalizationReferenceConfig":
        if self.black_percentile >= self.white_percentile:
            raise ValueError("reference black_percentile must be lower than white_percentile")
        if not math.isfinite(self.black_value) or not math.isfinite(self.white_value):
            raise ValueError("reference bounds must be finite")
        if self.black_value >= self.white_value:
            raise ValueError("reference black_value must be lower than white_value")
        return self


class PlaneNormalizationConfig(GalaxyProjectModel):
    mode: Literal["native", "percentile", "fixed_bounds"] = "native"
    black_percentile: float = Field(default=0.5, ge=0, le=100)
    white_percentile: float = Field(default=99.5, ge=0, le=100)
    black_value: float | None = None
    white_value: float | None = None
    reference: NormalizationReferenceConfig | None = None
    stretch: Literal["linear", "asinh", "gamma"] = "asinh"
    stretch_parameter: float = Field(default=4.0, gt=0)
    gain: float = Field(default=1.0, ge=0)

    @model_validator(mode="after")
    def validate_percentile_order(self) -> "PlaneNormalizationConfig":
        if self.black_percentile >= self.white_percentile:
            raise ValueError("normalization black_percentile must be lower than white_percentile")
        if self.mode == "fixed_bounds":
            if self.black_value is None or self.white_value is None:
                raise ValueError("fixed_bounds normalization requires black_value and white_value")
            if not math.isfinite(self.black_value) or not math.isfinite(self.white_value):
                raise ValueError("normalization bounds must be finite")
            if self.black_value >= self.white_value:
                raise ValueError("normalization black_value must be lower than white_value")
        if self.reference is not None:
            if self.mode != "fixed_bounds":
                raise ValueError("normalization reference requires fixed_bounds mode")
            if (self.black_value, self.white_value) != (
                self.reference.black_value, self.reference.white_value,
            ):
                raise ValueError("normalization bounds must match the locked reference")
        return self


class PlaneMappingConfig(GalaxyProjectModel):
    plane: str | None = None
    filter: str | None = None
    label: str | None = None
    rgb: RGBMixConfig = Field(default_factory=RGBMixConfig)
    normalization: PlaneNormalizationConfig | None = None

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
    normalization: PlaneNormalizationConfig = Field(default_factory=PlaneNormalizationConfig)


class MappingConfig(GalaxyProjectModel):
    defaults: MappingDefaults = Field(default_factory=MappingDefaults)
    planes: list[PlaneMappingConfig] = Field(default_factory=list)
    derived_planes: list[DerivedPlaneConfig] = Field(default_factory=list)


class StretchConfig(GalaxyProjectModel):
    kind: Literal["linear", "asinh", "gamma", "ghs"] = "asinh"
    parameter: float | None = Field(default=None, gt=0)
    stretch_factor: float | None = Field(default=None, ge=0, le=20)
    local_intensity: float | None = Field(default=None, ge=-5, le=15)
    symmetry_point: float | None = Field(default=None, ge=0, le=1)
    shadow_protection: float | None = Field(default=None, ge=0, le=1)
    highlight_protection: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_method_parameters(self) -> "StretchConfig":
        ghs_fields = (
            self.stretch_factor, self.local_intensity, self.symmetry_point,
            self.shadow_protection, self.highlight_protection,
        )
        if self.kind in {"asinh", "gamma"} and self.parameter is None:
            raise ValueError(f"{self.kind} stretch requires parameter")
        if self.kind == "linear" and self.parameter is not None:
            raise ValueError("linear stretch does not accept parameter")
        if self.kind != "ghs" and any(value is not None for value in ghs_fields):
            raise ValueError("GHS parameters require kind='ghs'")
        if self.kind == "ghs":
            if any(value is None for value in ghs_fields):
                raise ValueError("ghs stretch requires all five GHS parameters")
            assert self.shadow_protection is not None
            assert self.symmetry_point is not None
            assert self.highlight_protection is not None
            if not (
                self.shadow_protection <= self.symmetry_point
                <= self.highlight_protection
            ):
                raise ValueError(
                    "GHS parameters require shadow_protection <= symmetry_point "
                    "<= highlight_protection"
                )
        return self


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


class AutoStretchResolutionConfig(GalaxyProjectModel):
    algorithm_version: Literal["autostretch-shared-asinh-v1"] = "autostretch-shared-asinh-v1"
    reference_id: str
    branch: Literal["original", "deconvolved"]
    grid_id: str
    source_ids: list[str] = Field(min_length=1)
    sample_count: int = Field(ge=256)
    source_median: float = Field(gt=0, lt=0.1)
    robust_spread: float = Field(gt=0)
    object_fraction: float = Field(ge=0, le=0.25)
    target_median: Literal[0.1] = 0.1
    resolved_parameter: float = Field(gt=0)
    low_clipping_fraction: float = Field(ge=0, le=1)
    high_clipping_fraction: float = Field(ge=0, le=1)
    confidence: Literal["high", "qualified"]
    locked: Literal[True] = True


class ToneConfig(GalaxyProjectModel):
    stretch: ToneStretchSet
    percentiles: TonePercentiles
    gain: ToneGainBias = Field(default_factory=ToneGainBias)
    bias: ToneGainBias = Field(default_factory=lambda: ToneGainBias(red=0.0, green=0.0, blue=0.0))
    saturation: float = Field(default=1.0, ge=0)
    application: Literal["per_channel", "shared_intensity"] = "per_channel"
    shared_stretch: StretchConfig | None = None
    gamut_policy: Literal["clip", "rescale"] = "clip"
    auto_stretch: AutoStretchResolutionConfig | None = None

    @model_validator(mode="after")
    def validate_application(self) -> "ToneConfig":
        if self.application == "shared_intensity" and self.shared_stretch is None:
            raise ValueError("shared-intensity tone requires shared_stretch")
        if self.application == "per_channel" and self.shared_stretch is not None:
            raise ValueError("shared_stretch requires shared-intensity tone")
        if self.auto_stretch is not None:
            if self.application != "shared_intensity":
                raise ValueError("auto_stretch requires shared-intensity tone")
            if self.shared_stretch is None or self.shared_stretch.kind != "asinh":
                raise ValueError("auto_stretch requires the resolved shared asinh stretch")
            if self.shared_stretch.parameter != self.auto_stretch.resolved_parameter:
                raise ValueError("auto_stretch resolved parameter does not match shared_stretch")
        return self


class SkyRectangleConfig(GalaxyProjectModel):
    region_id: str
    center_ra_deg: float = Field(ge=0, lt=360)
    center_dec_deg: float = Field(ge=-90, le=90)
    width_arcsec: float = Field(gt=0)
    height_arcsec: float = Field(gt=0)


class BackgroundEstimatorConfig(GalaxyProjectModel):
    clip_sigma: float = Field(default=3.0, gt=0)
    max_iterations: int = Field(default=5, ge=1, le=50)
    minimum_samples: int = Field(default=256, ge=1)
    minimum_valid_fraction: float = Field(default=0.5, gt=0, le=1)


class ResolvedBackgroundPlaneConfig(GalaxyProjectModel):
    selection_key: str
    branch: Literal["original", "deconvolved"]
    grid_id: str
    source_ids: list[str]
    unit: str | None = None
    pedestal: float
    geometric_sample_count: int = Field(ge=1)
    common_valid_count: int = Field(ge=1)
    common_valid_fraction: float = Field(gt=0, le=1)
    sample_count: int = Field(ge=1)
    rejected_count: int = Field(ge=0)
    median: float
    robust_spread: float = Field(ge=0)
    residual_median: float


class BackgroundConfig(GalaxyProjectModel):
    mode: Literal["off", "pedestal"] = "off"
    black_reference_policy: Literal["legacy_percentile", "corrected_zero"] = "legacy_percentile"
    inclusion_regions: list[SkyRectangleConfig] = Field(default_factory=list)
    exclusion_regions: list[SkyRectangleConfig] = Field(default_factory=list)
    estimator: BackgroundEstimatorConfig = Field(default_factory=BackgroundEstimatorConfig)
    resolved_branches: dict[str, dict[str, ResolvedBackgroundPlaneConfig]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mode(self) -> "BackgroundConfig":
        inclusion_ids = [region.region_id for region in self.inclusion_regions]
        exclusion_ids = [region.region_id for region in self.exclusion_regions]
        if len(inclusion_ids) != len(set(inclusion_ids)):
            raise ValueError("background inclusion region IDs must be unique")
        if len(exclusion_ids) != len(set(exclusion_ids)):
            raise ValueError("background exclusion region IDs must be unique")
        if set(inclusion_ids) & set(exclusion_ids):
            raise ValueError("background inclusion and exclusion region IDs must be distinct")
        if set(self.resolved_branches) - {"original", "deconvolved"}:
            raise ValueError("background resolved branches must be original or deconvolved")
        if self.mode == "off" and self.black_reference_policy != "legacy_percentile":
            raise ValueError("background off mode requires legacy_percentile black reference")
        if self.mode == "pedestal" and not self.inclusion_regions:
            raise ValueError("background pedestal mode requires an inclusion region")
        return self


class PSFPlaneConfig(GalaxyProjectModel):
    enabled: bool = False
    kernel_path: str | None = None
    max_iterations: int = Field(default=10, ge=1, le=100)
    regularization: float = Field(default=0.0, ge=0.0)


class PSFConfig(GalaxyProjectModel):
    enabled: bool = False
    common_psf_fwhm_arcsec: float | None = Field(default=None, gt=0)
    per_plane: dict[str, PSFPlaneConfig] = Field(default_factory=dict)


class BridgeConfig(GalaxyProjectModel):
    enabled: StrictBool = True


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
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    tone: ToneConfig
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
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

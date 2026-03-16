from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class CircleRegion(BaseModel):
    kind: Literal["circle"]
    radius_arcmin: float = Field(gt=0)


class BoxRegion(BaseModel):
    kind: Literal["box"]
    width_arcmin: float = Field(gt=0)
    height_arcmin: float = Field(gt=0)


class PolygonRegion(BaseModel):
    kind: Literal["polygon"]
    vertices: list[tuple[float, float]] = Field(min_length=3)


RegionDefinition = CircleRegion | BoxRegion | PolygonRegion


class TargetConfig(BaseModel):
    name: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    ra: str | None = None
    dec: str | None = None
    region: RegionDefinition

    @model_validator(mode="after")
    def validate_target(self) -> "TargetConfig":
        if self.name:
            return self
        if self.ra_deg is not None and self.dec_deg is not None:
            return self
        if self.ra and self.dec:
            return self
        raise ValueError("target must specify either name, decimal coordinates, or sexagesimal coordinates")


class SearchConfig(BaseModel):
    missions: list[str] = Field(default_factory=lambda: ["HST", "JWST"])
    instruments: list[str] = Field(default_factory=list)
    detectors: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=lambda: ["SCIENCE", "DRZ", "DRC", "I2D"])
    observation_date_start: str | None = None
    observation_date_end: str | None = None


class CanvasCenterResolvedTarget(BaseModel):
    mode: Literal["resolved_target"]


class CanvasCenterExplicit(BaseModel):
    mode: Literal["explicit"]
    ra_deg: float
    dec_deg: float


CanvasCenter = CanvasCenterResolvedTarget | CanvasCenterExplicit


class CanvasConfig(BaseModel):
    center: CanvasCenter
    projection: str = "TAN"
    pixel_scale_arcsec: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation_deg: float = 0.0
    flux_conserving: bool = True


class PlanesConfig(BaseModel):
    enabled_filters: list[str] = Field(default_factory=list)
    disabled_plane_ids: list[str] = Field(default_factory=list)
    export_multiplane_fits: bool = True


class ChannelContribution(BaseModel):
    plane: str
    weight: float = 1.0


class DerivedPlaneConfig(BaseModel):
    name: str
    operation: Literal["linear_combination", "ratio"]
    terms: list[ChannelContribution] = Field(default_factory=list)
    numerator: list[ChannelContribution] = Field(default_factory=list)
    denominator: list[ChannelContribution] = Field(default_factory=list)
    epsilon: float = 1e-6

    @model_validator(mode="after")
    def validate_operands(self) -> "DerivedPlaneConfig":
        if self.operation == "linear_combination" and not self.terms:
            raise ValueError("linear_combination derived planes require terms")
        if self.operation == "ratio" and (not self.numerator or not self.denominator):
            raise ValueError("ratio derived planes require numerator and denominator terms")
        return self


class MappingDefaults(BaseModel):
    strategy: Literal["wavelength_order"] = "wavelength_order"


class MappingConfig(BaseModel):
    defaults: MappingDefaults = Field(default_factory=MappingDefaults)
    channels: dict[str, list[ChannelContribution]] = Field(
        default_factory=lambda: {"red": [], "green": [], "blue": []}
    )
    derived_planes: list[DerivedPlaneConfig] = Field(default_factory=list)

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, value: dict[str, list[ChannelContribution]]) -> dict[str, list[ChannelContribution]]:
        required = {"red", "green", "blue"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"mapping.channels missing required keys: {sorted(missing)}")
        return value


class StretchConfig(BaseModel):
    kind: Literal["asinh", "gamma"] = "asinh"
    parameter: float = Field(gt=0)


class ToneStretchSet(BaseModel):
    red: StretchConfig
    green: StretchConfig
    blue: StretchConfig


class TonePercentiles(BaseModel):
    black: float = Field(ge=0, le=100)
    white: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> "TonePercentiles":
        if self.black >= self.white:
            raise ValueError("tone.percentiles.black must be lower than tone.percentiles.white")
        return self


class ToneGainBias(BaseModel):
    red: float = 1.0
    green: float = 1.0
    blue: float = 1.0


class ToneConfig(BaseModel):
    stretch: ToneStretchSet
    percentiles: TonePercentiles
    gain: ToneGainBias = Field(default_factory=ToneGainBias)
    bias: ToneGainBias = Field(default_factory=lambda: ToneGainBias(red=0.0, green=0.0, blue=0.0))
    saturation: float = Field(default=1.0, ge=0)


class PSFPlaneConfig(BaseModel):
    enabled: bool = False
    kernel_path: str | None = None
    max_iterations: int = Field(default=10, ge=1, le=100)
    regularization: float = Field(default=0.0, ge=0.0)


class PSFConfig(BaseModel):
    enabled: bool = False
    common_psf_fwhm_arcsec: float | None = Field(default=None, gt=0)
    per_plane: dict[str, PSFPlaneConfig] = Field(default_factory=dict)


class ExecutionConfig(BaseModel):
    fail_fast: bool = False


class GalaxyConfig(BaseModel):
    target: TargetConfig
    search: SearchConfig = Field(default_factory=SearchConfig)
    canvas: CanvasConfig
    planes: PlanesConfig = Field(default_factory=PlanesConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    tone: ToneConfig
    psf: PSFConfig = Field(default_factory=PSFConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def load_config(path: str | Path) -> GalaxyConfig:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return GalaxyConfig.model_validate(data)


def dump_config(config: GalaxyConfig, path: str | Path) -> None:
    Path(path).write_text(config.to_yaml(), encoding="utf-8")


def validate_config_dict(data: dict[str, Any]) -> tuple[GalaxyConfig | None, list[str]]:
    try:
        return GalaxyConfig.model_validate(data), []
    except ValidationError as exc:
        return None, [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]

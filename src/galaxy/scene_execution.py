"""Translate a validated scene card into an immutable processing launch view."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .processing_config import GalaxyConfig
from .scene_card import asset_path, dependency_issues
from .scene_models import SceneCard, document
from .scene_readiness import ReadinessIssue, readiness
from .selection import CandidateManifest, CandidateRecord, SelectionInputs


@dataclass(frozen=True, slots=True)
class SceneExecution:
    card: SceneCard
    config: GalaxyConfig
    selection_manifest: CandidateManifest
    local_product_paths: dict[str, Path]


class SceneNotReadyError(ValueError):
    def __init__(self, issues: list[ReadinessIssue]):
        self.issues = issues
        super().__init__("\n".join(f"{item.path}: [{item.code}] {item.message}" for item in issues))


def prepare_scene_execution(card: SceneCard, card_path: str | Path) -> SceneExecution:
    """Freeze current scene settings and exact product pins for pipeline launch."""
    frozen = SceneCard.model_validate(document(card))
    issues = [
        item for item in readiness(frozen, "render", plane_filters=None)
        if item.code != "inspection_required"
    ]
    if issues:
        raise SceneNotReadyError(issues)

    data = document(frozen)
    canvas = dict(data["canvas"])
    canvas.pop("view_state", None)
    target_data = data.get("target")
    target: dict[str, Any] | None = None
    if target_data and "region" in target_data:
        target = {key: value for key, value in target_data.items() if key != "coordinate_frame"}

    search = {
        "missions": [], "instruments": [], "detectors": [], "filters": [], "product_types": [],
        "observation_selection": "all", "max_observations_per_filter": 1,
        **data.get("search", {}),
    }
    products = {product.product_id: product for product in frozen.selection.products or []}
    selected_ids = frozen.selection.selected_product_ids or []
    search["source_products"] = [
        {
            "stable_product_identifier": products[product_id].product_id,
            "product_filename": products[product_id].filename,
            "data_uri": products[product_id].data_uri,
            "obs_id": products[product_id].observation_id,
            "mission": products[product_id].mission,
            "instrument": products[product_id].instrument,
            "detector": products[product_id].detector,
            "filter": products[product_id].filter,
            "product_type": products[product_id].product_type,
            "product_version": products[product_id].product_version,
        }
        for product_id in selected_ids
    ]
    mapping = {
        "defaults": {"strategy": "continuum"}, "planes": [], "derived_planes": [],
        **data["mapping"],
    }
    planes = {
        "enabled_filters": [], "disabled_plane_ids": [], "export_multiplane_fits": False,
        **data["planes"],
    }
    tone = dict(data["tone"])
    psf = {"enabled": False, "per_plane": {}, **data["psf"]}
    execution = {
        "fail_fast": False, "log_file": "galaxy.log",
        "debug_to_console": False, "debug_to_file": True,
        **data.get("execution", {}),
    }

    assets = frozen.assets or {}
    for plane_id, policy in psf["per_plane"].items():
        kernel_id = policy.pop("kernel_asset_id", None)
        if kernel_id is None:
            continue
        asset = assets[kernel_id]
        if asset.path is None:
            raise SceneNotReadyError([ReadinessIssue(
                f"psf.per_plane.{plane_id}.kernel_asset_id",
                "pipeline execution requires a locally available kernel asset", "dependency",
            )])
        policy["kernel_path"] = str(asset_path(card_path, asset))

    config = GalaxyConfig.model_validate({
        "target": target,
        "search": search,
        "canvas": canvas,
        "planes": planes,
        "mapping": mapping,
        "tone": tone,
        "psf": psf,
        "execution": execution,
    })
    candidates: list[CandidateRecord] = []
    local: dict[str, Path] = {}
    dependency_by_id = {item.asset_id: item for item in dependency_issues(frozen, card_path)}
    for index, product_id in enumerate(selected_ids):
        product = products[product_id]
        if product.cached_asset_id:
            if product.cached_asset_id in dependency_by_id:
                issue = dependency_by_id[product.cached_asset_id]
                raise SceneNotReadyError([ReadinessIssue(
                    f"selection.products.{index}.cached_asset_id", issue.message, "dependency"
                )])
            local[product_id] = asset_path(card_path, assets[product.cached_asset_id])
        elif not product.data_uri:
            raise SceneNotReadyError([ReadinessIssue(
                f"selection.products.{index}.data_uri",
                "selected product requires data_uri or a local cached source asset", "dependency",
            )])
        candidates.append(CandidateRecord(
            candidate_id=product_id,
            obsid=product.observation_id,
            obs_id=product.observation_id,
            product_filename=product.filename,
            data_uri=product.data_uri,
            mission=product.mission,
            instrument=product.instrument,
            detector=product.detector,
            filter_name=product.filter,
            product_type=product.product_type,
            product_version=product.product_version,
            observation_date_start=product.observed_at,
            observation_date_end=product.observed_at,
            exposure_time=product.exposure_seconds,
            file_size=None,
            proposal_id=None,
            proposal_title=None,
            target_name=frozen.target.resolved_name if frozen.target else None,
            selection_rank=[0, index, [0], product_id],
            auto_selected=False,
            auto_selection_reason="selected:pinned_scene_card",
            user_selected=True,
            selected=True,
            selected_reason="selected:pinned_scene_card",
            extra_metadata={"scene_product_id": product_id},
        ))
    manifest = CandidateManifest(
        generated_at=frozen.updated_at,
        config_path=str(Path(card_path).resolve()),
        selection_policy="pinned_scene_card",
        max_observations_per_filter=max(len(candidates), 1),
        candidates=candidates,
        selection_inputs=SelectionInputs(include_products=set(selected_ids)),
    )
    return SceneExecution(frozen, config, manifest, local)

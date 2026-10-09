from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import astroquery
import astropy
import numpy
import reproject
import scipy

from galaxy.bridge import BridgeProfile
from galaxy.processing_config import GalaxyConfig
from galaxy.planes import PlaneRecord
from galaxy.selection import CandidateManifest
from galaxy.targeting import ResolvedTarget


def build_provenance(
    config: GalaxyConfig,
    resolved_target: ResolvedTarget,
    manifest: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    plane_records: list[PlaneRecord],
    reprojection_settings: dict[str, Any],
    candidate_manifest: CandidateManifest | None = None,
    execution_source: str = "raw_config_discovery",
    display_warnings: list[str] | None = None,
    stage_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selection_section = {
        "source": execution_source,
        "policy": config.search.observation_selection,
        "max_observations_per_filter": config.search.max_observations_per_filter,
        "explicit_overrides": {},
        "final_selected_candidate_ids": [],
    }
    if candidate_manifest is not None:
        selection_section = {
            "source": execution_source,
            "policy": candidate_manifest.selection_policy,
            "max_observations_per_filter": candidate_manifest.max_observations_per_filter,
            "explicit_overrides": candidate_manifest.selection_inputs.to_dict(),
            "final_selected_candidate_ids": [candidate.candidate_id for candidate in candidate_manifest.candidates if candidate.selected],
            "candidate_manifest": {
                "config_path": candidate_manifest.config_path,
                "generated_at": candidate_manifest.generated_at,
                "candidate_count": len(candidate_manifest.candidates),
            },
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {
            "input": config.target.model_dump(mode="json") if config.target is not None else None,
            "resolved_ra_deg": resolved_target.coord.ra.deg,
            "resolved_dec_deg": resolved_target.coord.dec.deg,
            "resolution_source": resolved_target.source,
            "region": resolved_target.region,
        },
        "selection": selection_section,
        "source_files": manifest,
        "skipped_products": skipped,
        "planes": [asdict(record) for record in plane_records],
        "reprojection": reprojection_settings,
        "bridge": {"enabled": config.bridge.enabled, **BridgeProfile().identity()},
        "psf": config.psf.model_dump(mode="json"),
        "mapping": config.mapping.model_dump(mode="json"),
        "tone": config.tone.model_dump(mode="json"),
        "tone_algorithms": _tone_algorithm_record(config),
        "display": {"warnings": display_warnings or []},
        "stage_records": stage_records or [],
        "software_versions": {
            "galaxy": "0.1.0",
            "astropy": astropy.__version__,
            "astroquery": astroquery.__version__,
            "numpy": numpy.__version__,
            "reproject": reproject.__version__,
            "scipy": scipy.__version__,
        },
    }


def _tone_algorithm_record(config: GalaxyConfig) -> dict[str, Any]:
    tone = config.tone
    methods = (
        [tone.shared_stretch.kind] if tone.shared_stretch is not None
        else [getattr(tone.stretch, channel).kind for channel in ("red", "green", "blue")]
    )
    versions = {"tone_application": "tone-v2"}
    if "ghs" in methods:
        versions["ghs_equations"] = "ghs-process-doc-3.0.4"
    if tone.auto_stretch is not None:
        versions["auto_stretch"] = tone.auto_stretch.algorithm_version
    return {
        "application": tone.application,
        "methods": methods,
        "gamut_policy": tone.gamut_policy,
        "algorithm_versions": versions,
    }


def write_provenance(document: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(document, indent=2), encoding="utf-8")

"""UI-independent behavior for the five-screen scene-card workflow."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from astropy.io import fits

from .processing_config import PlaneNormalizationConfig
from .scene_card import (
    DependencyIssue, asset_path, create_scene, dependency_issues, duplicate_scene,
    edit_scene, load_scene, save_scene, utc_now,
)
from .scene_models import Asset, Export, SceneCard, bridge_snapshot_matches, document, effective_inputs
from .scene_readiness import ReadinessIssue, readiness
from .selection import (
    CandidateManifest, CandidateRecord, load_candidate_manifest, write_candidate_manifest,
)
from .mapping import default_plane_mappings
from .discovery_sources import DiscoveryHint
from .targeting import ResolverMatch


class Screen(str, Enum):
    DISCOVERY = "Discovery"
    REFINEMENT = "Scene refinement"
    RENDER = "Render and adjust"
    OUTPUT = "Output and save"
    LIBRARY = "Saved scenes"


class OperationPhase(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LibraryOrigin(str, Enum):
    BUNDLED_EXAMPLE = "bundled_example"
    USER_SCENE = "user_scene"


@dataclass(frozen=True, slots=True)
class InputRoute:
    kind: Literal["scene", "manifest", "planes"]
    path: Path
    screen: Screen


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    path: Path
    card: SceneCard | None
    error: str | None
    dependencies: tuple[DependencyIssue, ...] = ()
    render_issues: tuple[ReadinessIssue, ...] = ()
    thumbnail_path: Path | None = None
    thumbnail_kind: str = "placeholder"
    origin: LibraryOrigin = LibraryOrigin.USER_SCENE

    @property
    def readiness_label(self) -> str:
        if self.card is None:
            return "Invalid"
        return "Render ready" if not self.render_issues else "Draft"


@dataclass(frozen=True, slots=True)
class ProjectLibrary:
    examples: tuple[LibraryEntry, ...]
    saved_scenes: tuple[LibraryEntry, ...]


@dataclass(frozen=True, slots=True)
class DeletedProject:
    recovery_directory: Path
    card_path: Path
    asset_root: Path | None


@dataclass(frozen=True, slots=True)
class SourceArtifactRecord:
    product_id: str
    mission: str | None
    filter_name: str | None
    processing_level: str | None
    filename: str | None
    status: Literal["remote_only", "available_local", "missing", "corrupt"]
    path: Path | None = None
    asset_id: str | None = None
    native_unit: str | None = None
    mask_sources: tuple[str, ...] = ()
    normalization_mode: str = "native"
    black_percentile: float | None = None
    white_percentile: float | None = None
    plane_gain: float = 1.0
    valid_coverage_fraction: float | None = None
    rgb_contribution_percent: dict[str, float] | None = None


@dataclass(frozen=True, slots=True)
class AssetArtifactRecord:
    asset_id: str
    kind: str
    status: Literal["remote_only", "available_local", "missing", "corrupt"]
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class RenderArtifactRecord:
    render_id: str
    branch: str
    revision: int
    state: Literal["current", "stale"]


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    sources: tuple[SourceArtifactRecord, ...]
    assets: tuple[AssetArtifactRecord, ...]
    renders: tuple[RenderArtifactRecord, ...]
    export_count: int
    warnings: tuple[str, ...] = ()

    def asset_count(self, kind: str) -> int:
        return sum(item.kind == kind for item in self.assets)

    @property
    def remote_source_count(self) -> int:
        return sum(item.status == "remote_only" for item in self.sources)

    @property
    def local_source_count(self) -> int:
        return sum(item.status == "available_local" for item in self.sources)

    @property
    def issue_count(self) -> int:
        declared_assets = {item.asset_id for item in self.assets}
        asset_issues = sum(item.status in {"missing", "corrupt"} for item in self.assets)
        unresolved_products = sum(
            item.status in {"missing", "corrupt"}
            and (item.asset_id is None or item.asset_id not in declared_assets)
            for item in self.sources
        )
        return asset_issues + unresolved_products


def classify_input(path: str | Path) -> InputRoute:
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise ValueError(f"input does not exist or is not a file: {candidate}")
    if candidate.suffix.lower() in {".fits", ".fit", ".fts"}:
        return InputRoute("planes", candidate, Screen.RENDER)
    if candidate.suffix.lower() != ".json":
        raise ValueError("UI input must be a scene card JSON, candidate manifest JSON, or FITS artifact")
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON input {candidate}: {exc}") from exc
    if isinstance(payload, dict) and payload.get("document_type") == "galaxy.scene_card":
        load_scene(candidate)
        return InputRoute("scene", candidate, Screen.REFINEMENT)
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        load_candidate_manifest(candidate)
        return InputRoute("manifest", candidate, Screen.REFINEMENT)
    raise ValueError(f"unrecognized JSON artifact: {candidate}")


def resolve_workdir_input(path: str | Path) -> InputRoute:
    candidate = Path(path).resolve()
    if candidate.is_file():
        return classify_input(candidate)
    if not candidate.is_dir():
        raise ValueError(f"input does not exist: {candidate}")
    for name in (
        "original/aligned-planes.fits",
        "deconvolved/aligned-planes.fits",
        "exported_planes.fits",
        "exported_planes_deconvolved.fits",
        "candidates.json",
    ):
        match = candidate / Path(name)
        if match.is_file():
            return classify_input(match)
    for match in sorted(candidate.glob("*.json")):
        try:
            route = classify_input(match)
        except ValueError:
            continue
        if route.kind == "scene":
            return route
    raise ValueError(f"workdir contains no supported Galaxy artifact: {candidate}")


def discover_workspace_inputs(root: str | Path) -> list[InputRoute]:
    """List choices without selecting one; normal startup still opens Discovery."""
    base = Path(root).resolve()
    found: dict[Path, InputRoute] = {}
    for search_root in (base / "artifacts",):
        if not search_root.is_dir():
            continue
        for pattern in ("**/aligned-planes.fits", "**/exported_planes.fits", "**/exported_planes_deconvolved.fits",
                        "**/candidates.json", "**/*.scene.json"):
            for candidate in search_root.glob(pattern):
                try:
                    route = classify_input(candidate)
                except ValueError:
                    continue
                found[route.path] = route
    order = {"planes": 0, "manifest": 1, "scene": 2}
    return sorted(found.values(), key=lambda item: (order[item.kind], str(item.path).lower()))


def list_scene_library(scene_directory: str | Path) -> list[LibraryEntry]:
    directory = Path(scene_directory).resolve()
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError(f"scene library is not a directory: {directory}")
    entries: list[LibraryEntry] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("document_type") != "galaxy.scene_card":
                continue
            card = load_scene(path)
            problems = tuple(render_issues(card))
            dependencies = tuple(dependency_issues(card, path))
            thumbnail, kind = _thumbnail(card, path, dependencies)
            entries.append(LibraryEntry(path, card, None, dependencies, problems, thumbnail, kind))
        except Exception as exc:
            entries.append(LibraryEntry(path, None, str(exc)))
    return sorted(entries, key=lambda item: item.card.updated_at if item.card else "", reverse=True)


def list_project_library(scene_directory: str | Path, project_root: str | Path) -> ProjectLibrary:
    """Return separately owned example and user-scene entries with deterministic deduplication."""
    user_entries = [
        LibraryEntry(
            entry.path, entry.card, entry.error, entry.dependencies, entry.render_issues,
            entry.thumbnail_path, entry.thumbnail_kind, LibraryOrigin.USER_SCENE,
        )
        for entry in list_scene_library(scene_directory)
    ]
    user_by_path = {str(entry.path.resolve()).casefold(): entry for entry in user_entries}
    examples: list[LibraryEntry] = []
    for entry in list_scene_library(Path(project_root).resolve() / "examples"):
        if entry.card is None:
            continue
        user_copy = user_by_path.get(
            str(example_user_path(entry.path, scene_directory)).casefold()
        )
        examples.append(LibraryEntry(
            entry.path, entry.card, entry.error, entry.dependencies, entry.render_issues,
            user_copy.thumbnail_path if user_copy and user_copy.card else None,
            user_copy.thumbnail_kind if user_copy and user_copy.card else "placeholder",
            LibraryOrigin.BUNDLED_EXAMPLE,
        ))
    seen_paths = {str(entry.path.resolve()).casefold() for entry in examples}
    saved: list[LibraryEntry] = []
    for entry in user_entries:
        equivalent_path = str(entry.path.resolve()).casefold() in seen_paths
        if equivalent_path:
            continue
        saved.append(entry)
    return ProjectLibrary(tuple(examples), tuple(saved))


def inspect_scene_artifacts(card: SceneCard, card_path: str | Path | None) -> ArtifactInventory:
    """Derive the declared artifact inventory; unrelated filesystem files are never scanned."""
    issues: dict[str, DependencyIssue] = {}
    if card_path is not None:
        issues = {issue.asset_id: issue for issue in dependency_issues(card, card_path)}

    def asset_status(asset_id: str) -> tuple[str, Path | None]:
        asset = (card.assets or {}).get(asset_id)
        if asset is None:
            return "missing", None
        if asset.path is None:
            return "remote_only", None
        path = asset_path(card_path, asset) if card_path is not None else None
        issue = issues.get(asset_id)
        if issue is None:
            return ("available_local", path) if card_path is not None else ("missing", path)
        return ("missing" if issue.code == "missing" else "corrupt"), path

    selected = set(card.selection.selected_product_ids or []) if card.selection else set()
    rendered_diagnostics = _current_plane_diagnostics(card, card_path)
    sources: list[SourceArtifactRecord] = []
    for product in card.selection.products or [] if card.selection else []:
        if product.product_id not in selected:
            continue
        if product.cached_asset_id:
            status, path = asset_status(product.cached_asset_id)
        elif product.data_uri:
            status, path = "remote_only", None
        else:
            status, path = "missing", None
        native_unit, mask_sources = _source_fits_display_metadata(path) if path and path.is_file() else (None, ())
        normalization = _effective_normalization(card, product.filter)
        plane_id = Path(product.filename).stem if product.filename else ""
        rendered = rendered_diagnostics.get(plane_id, {})
        sources.append(SourceArtifactRecord(
            product.product_id, product.mission, product.filter, product.product_version,
            product.filename, status, path, product.cached_asset_id,
            native_unit or _string_or_none(rendered.get("native_unit")),
            mask_sources or tuple(str(item) for item in rendered.get("mask_sources", [])),
            str(rendered.get("normalization_mode") or normalization.mode),
            _float_or_none(rendered.get("black_percentile")) if rendered else (
                normalization.black_percentile if normalization.mode == "percentile" else None
            ),
            _float_or_none(rendered.get("white_percentile")) if rendered else (
                normalization.white_percentile if normalization.mode == "percentile" else None
            ),
            _float_or_none(rendered.get("plane_gain")) or normalization.gain,
            _float_or_none(rendered.get("valid_coverage_fraction")),
            rendered.get("rgb_contribution_percent") if isinstance(rendered.get("rgb_contribution_percent"), dict) else None,
        ))
    assets: list[AssetArtifactRecord] = []
    for asset_id, asset in (card.assets or {}).items():
        status, path = asset_status(asset_id)
        assets.append(AssetArtifactRecord(asset_id, asset.kind, status, path))
    current_ids = {
        record.render_id for branch in ("original", "deconvolved")
        for record in [matching_render(card, branch)] if record is not None
    }
    renders = tuple(
        RenderArtifactRecord(record.render_id, record.branch, record.content_revision,
                             "current" if record.render_id in current_ids else "stale")
        for record in card.renders or []
    )
    units = {item.native_unit.casefold() for item in sources if item.native_unit}
    warnings: list[str] = []
    if len(units) > 1 and any(item.normalization_mode == "native" for item in sources):
        warnings.append(
            "Mixed native FITS units are selected while native normalization is enabled; "
            "some planes may be visually suppressed."
        )
    return ArtifactInventory(tuple(sources), tuple(assets), renders, len(card.exports or []), tuple(warnings))


def _effective_normalization(card: SceneCard, filter_name: str | None) -> PlaneNormalizationConfig:
    defaults: dict[str, object] = {}
    if card.mapping and card.mapping.defaults and card.mapping.defaults.normalization:
        defaults = card.mapping.defaults.normalization.model_dump(exclude_none=True)
    override: dict[str, object] = {}
    for contribution in card.mapping.planes or [] if card.mapping else []:
        if contribution.filter and contribution.filter.upper() == str(filter_name or "").upper():
            if contribution.normalization:
                override = contribution.normalization.model_dump(exclude_none=True)
            break
    return PlaneNormalizationConfig.model_validate({**defaults, **override})


def _source_fits_display_metadata(path: Path) -> tuple[str | None, tuple[str, ...]]:
    try:
        with fits.open(path, memmap=True, lazy_load_hdus=True) as hdul:
            science = next((hdu for hdu in hdul if str(hdu.name).upper() == "SCI"), hdul[0])
            native_unit = science.header.get("BUNIT") or hdul[0].header.get("BUNIT")
            mask_sources = tuple(
                name for name in ("DQ", "WHT", "CTX")
                if any(str(hdu.name).upper() == name for hdu in hdul)
            )
            return _string_or_none(native_unit), mask_sources
    except (OSError, ValueError):
        return None, ()


def _current_plane_diagnostics(
    card: SceneCard, card_path: str | Path | None
) -> dict[str, dict[str, object]]:
    if card_path is None:
        return {}
    render = matching_render(card, "original")
    if render is None or not card.assets:
        return {}
    asset = card.assets.get(render.provenance_asset_id)
    if asset is None or asset.path is None:
        return {}
    path = asset_path(card_path, asset)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return {
        str(item.get("plane_id")): item
        for item in payload.get("planes", [])
        if (
            isinstance(item, dict)
            and item.get("plane_id")
            and item.get("artifact_branch", "original") == "original"
        )
    }


def _string_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _thumbnail(
    card: SceneCard, card_path: Path, dependencies: tuple[DependencyIssue, ...]
) -> tuple[Path | None, str]:
    asset_id = card.thumbnail_asset_id
    if asset_id and card.assets and card.assets[asset_id].kind == "render_thumbnail" and matching_render(card) is None:
        return None, "placeholder"
    if not asset_id or not card.assets or asset_id not in card.assets:
        return None, "placeholder"
    if any(issue.asset_id == asset_id for issue in dependencies):
        return None, "placeholder"
    asset = card.assets[asset_id]
    if asset.path is None:
        kind = "external discovery image" if asset.kind == "discovery_thumbnail" else "placeholder"
        return None, kind
    kind = "external discovery image" if asset.kind == "discovery_thumbnail" else "Galaxy preview"
    return asset_path(card_path, asset), kind


def scene_filename(title: str, scene_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled-scene"
    return f"{slug[:64]}-{scene_id[:8]}.scene.json"


def default_scene_path(card: SceneCard, scene_directory: str | Path) -> Path:
    return Path(scene_directory).resolve() / scene_filename(card.title, card.scene_id)


def associated_asset_root(card_path: str | Path) -> Path:
    path = Path(card_path).resolve()
    if path.name.endswith(".scene.json"):
        name = f"{path.name[:-len('.scene.json')]}.assets"
    else:
        name = path.stem
    return path.parent / name


def delete_library_scene(
    entry: LibraryEntry,
    scene_directory: str | Path,
    *,
    move: Callable[[str | Path, str | Path], object] = os.replace,
    transaction_id: str | None = None,
) -> DeletedProject:
    """Move one user scene and its optional asset root into recoverable storage."""
    if entry.origin is not LibraryOrigin.USER_SCENE:
        raise ValueError("bundled examples cannot be deleted")
    if entry.card is None:
        raise ValueError("invalid scene cards cannot be deleted")
    directory = Path(scene_directory).resolve()
    source = entry.path.resolve()
    if source.parent != directory or not source.is_file():
        raise ValueError("scene deletion target must be a scene-card file in the scene directory")
    if _is_reparse_point(source):
        raise ValueError("scene deletion does not follow reparse-point scene cards")
    asset_root = associated_asset_root(source)
    if asset_root.exists():
        if asset_root.parent != directory or not asset_root.is_dir():
            raise ValueError("associated asset root must be a directory in the scene directory")
        if _is_reparse_point(asset_root):
            raise ValueError("scene deletion does not follow reparse-point asset roots")
    else:
        asset_root = None

    recovery_root = directory / ".galaxy-trash"
    recovery_root.mkdir(parents=True, exist_ok=True)
    recovery_directory = recovery_root / (transaction_id or str(uuid4()))
    recovery_directory.mkdir(exist_ok=False)
    targets = [source, *([asset_root] if asset_root is not None else [])]
    manifest_path = recovery_directory / "recovery.json"
    manifest_path.write_text(json.dumps({
        "deleted_at": utc_now(),
        "scene_id": entry.card.scene_id,
        "title": entry.card.title,
        "members": [
            {"original_path": str(target), "recovery_name": target.name}
            for target in targets
        ],
    }, indent=2), encoding="utf-8")
    moved: list[tuple[Path, Path]] = []
    try:
        for target in targets:
            destination = recovery_directory / target.name
            move(target, destination)
            moved.append((target, destination))
    except Exception as exc:
        rollback_errors: list[str] = []
        for original, recovered in reversed(moved):
            try:
                move(recovered, original)
            except Exception as rollback_exc:
                rollback_errors.append(f"{recovered} -> {original}: {rollback_exc}")
        if not rollback_errors:
            manifest_path.unlink(missing_ok=True)
            try:
                recovery_directory.rmdir()
            except OSError:
                pass
        suffix = "" if not rollback_errors else "; rollback failed: " + "; ".join(rollback_errors)
        raise OSError(f"project deletion failed and was rolled back: {exc}{suffix}") from exc
    return DeletedProject(recovery_directory, source, asset_root)


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & 0x400)


def save_draft(
    card: SceneCard, scene_directory: str | Path, path: str | Path | None = None
) -> tuple[SceneCard, Path]:
    destination = Path(path).resolve() if path is not None else default_scene_path(card, scene_directory)
    return save_scene(card, destination), destination


def example_user_path(example_path: str | Path, scene_directory: str | Path) -> Path:
    source = Path(example_path).resolve()
    if source.suffix.lower() != ".json":
        raise ValueError("bundled example must be a JSON scene card")
    return Path(scene_directory).resolve() / source.name


def materialize_example(
    example_path: str | Path, scene_directory: str | Path, *, overwrite: bool = False
) -> tuple[SceneCard, Path]:
    """Atomically copy a validated example JSON without touching its user asset root."""
    source = Path(example_path).resolve()
    card = load_scene(source)
    destination = example_user_path(source, scene_directory)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"example user copy already exists: {destination}")
    payload = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    copied = load_scene(destination)
    if copied.scene_id != card.scene_id:
        raise ValueError("materialized example changed scene identity")
    return copied, destination


def open_example_user_copy(
    example_path: str | Path, scene_directory: str | Path
) -> tuple[SceneCard, Path]:
    destination = example_user_path(example_path, scene_directory)
    if destination.exists():
        return load_scene(destination), destination
    return materialize_example(example_path, scene_directory)


def duplicate_library_scene(
    entry: LibraryEntry, scene_directory: str | Path
) -> tuple[SceneCard, Path]:
    if entry.card is None:
        raise ValueError("cannot duplicate an invalid scene card")
    if entry.origin is LibraryOrigin.BUNDLED_EXAMPLE:
        return materialize_example(entry.path, scene_directory)
    title = f"{entry.card.title} copy"
    identity = create_scene(title)
    destination = default_scene_path(identity, scene_directory)
    duplicate = duplicate_scene(
        entry.card,
        entry.path,
        destination,
        title=title,
        materialization="link_or_copy",
        identity=identity,
    )
    return duplicate, destination


def draft_from_target(
    *, name: str | None = None, ra_deg: float | None = None, dec_deg: float | None = None,
    region_kind: Literal["circle", "box"] = "box", radius_arcmin: float | None = None,
    width_arcmin: float | None = None, height_arcmin: float | None = None,
    resolved_name: str | None = None,
) -> SceneCard:
    title = (resolved_name or name or "Untitled scene").strip()
    target: dict[str, object] = {"coordinate_frame": "ICRS"}
    if name and name.strip():
        target["name"] = name.strip()
    if resolved_name and resolved_name.strip():
        target["resolved_name"] = resolved_name.strip()
    if ra_deg is not None or dec_deg is not None:
        if ra_deg is None or dec_deg is None:
            raise ValueError("RA and Dec must be supplied together")
        target.update(ra_deg=float(ra_deg), dec_deg=float(dec_deg))
    if region_kind == "circle":
        if radius_arcmin is None:
            raise ValueError("circle radius is required")
        target["region"] = {"kind": "circle", "radius_arcmin": float(radius_arcmin)}
    else:
        if width_arcmin is None or height_arcmin is None:
            raise ValueError("box width and height are required")
        target["region"] = {"kind": "box", "width_arcmin": float(width_arcmin),
                            "height_arcmin": float(height_arcmin)}
    card = edit_scene(create_scene(title), {"target": target, "search": default_search()})
    return initialize_canvas(card) if ra_deg is not None else card


def draft_from_discovery_hint(
    hint: DiscoveryHint, *, width_arcmin: float = 2.0, height_arcmin: float = 2.0
) -> SceneCard:
    """Convert a non-authoritative hint into search inputs and attributed UI state."""
    card = draft_from_target(
        name=hint.target_name,
        resolved_name=hint.target_name,
        ra_deg=hint.ra_deg,
        dec_deg=hint.dec_deg,
        width_arcmin=width_arcmin,
        height_arcmin=height_arcmin,
    )
    metadata: dict[str, object] = dict(hint.extracted_metadata)
    for key, value in {
        "target_name": hint.target_name,
        "proposal_id": hint.proposal_id,
        "observation_date": hint.observation_date,
        "instruments": list(hint.instruments) if hint.instruments else None,
        "filters": list(hint.filters) if hint.filters else None,
        "alignment_rotation_deg": hint.alignment.rotation_deg,
        "data_url": hint.data_url,
    }.items():
        if value is not None:
            metadata[key] = value
    changes: dict[str, object] = {
        "discovery": {"sources": [{
            "source_kind": "release_tracker", "source_url": hint.source_url,
            "retrieved_at": hint.retrieved_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "extracted_metadata": metadata,
        }]}
    }
    if hint.preview_url:
        thumbnail: dict[str, object] = {
            "kind": "discovery_thumbnail", "uri": hint.preview_url,
            "source_url": hint.source_url,
        }
        if hint.credit is not None:
            thumbnail["credit"] = hint.credit
        changes["assets"] = {"discovery-thumbnail": thumbnail}
        changes["thumbnail_asset_id"] = "discovery-thumbnail"
    data = document(card)
    data.update(changes)
    return SceneCard.model_validate(data)


def draft_from_resolver_match(
    query: str, match: ResolverMatch, source: str, *, region_size_arcmin: float
) -> SceneCard:
    resolved_name = match.label if match.label.strip() != query.strip() else None
    card = draft_from_target(
        name=query, resolved_name=resolved_name, ra_deg=match.ra_deg, dec_deg=match.dec_deg,
        width_arcmin=region_size_arcmin, height_arcmin=region_size_arcmin,
    )
    data = document(card)
    data["discovery"] = {"sources": [{
        "source_kind": "name_resolver",
        "source_url": "https://cds.unistra.fr/cgi-bin/Sesame",
        "retrieved_at": utc_now(),
        "extracted_metadata": {
            "query": query, "resolved_label": match.label, "resolver": source,
            "ra_deg": match.ra_deg, "dec_deg": match.dec_deg,
        },
    }]}
    return SceneCard.model_validate(data)


def default_search() -> dict[str, object]:
    return {
        "missions": ["HST", "JWST"], "instruments": [], "detectors": [], "filters": [],
        "product_types": ["SCIENCE", "DRZ", "DRC", "I2D"],
        "observation_selection": "deepest_per_filter", "max_observations_per_filter": 1,
    }


def initialize_canvas(card: SceneCard, *, reset: bool = False) -> SceneCard:
    if card.canvas is not None and not reset:
        return card
    target = card.target
    if target is None or target.ra_deg is None or target.dec_deg is None or target.region is None:
        raise ValueError("resolved coordinates and region dimensions are required for the default frame")
    region = target.region
    if region.kind == "circle" and region.radius_arcmin is not None:
        width_arcmin = height_arcmin = region.radius_arcmin * 2
    elif region.kind == "box" and region.width_arcmin is not None and region.height_arcmin is not None:
        width_arcmin, height_arcmin = region.width_arcmin, region.height_arcmin
    else:
        raise ValueError("complete circle or box region dimensions are required")
    return edit_scene(card, {"canvas": {
        "center": {"mode": "explicit", "ra_deg": target.ra_deg, "dec_deg": target.dec_deg},
        "projection": "TAN", "pixel_scale_arcsec": 1.0,
        "width": math.ceil(width_arcmin * 60), "height": math.ceil(height_arcmin * 60),
        "rotation_deg": 0.0, "flux_conserving": True, "frame_origin": "search_region",
    }})


def selected_fits_paths(
    card: SceneCard, card_path: str | Path,
) -> tuple[list[Path], list[str], list[str]]:
    """Resolve selected local FITS without searching outside the project's asset roots."""
    scene_path = Path(card_path).resolve()
    products = {item.product_id: item for item in (card.selection.products or [])} if card.selection else {}
    selected = card.selection.selected_product_ids or [] if card.selection else []
    roots = [
        associated_asset_root(scene_path),
        scene_path.parent / f"{scene_path.stem}.assets",
        scene_path.parent / scene_path.stem,
    ]
    found: list[Path] = []
    identities: list[str] = []
    errors: list[str] = []
    for product_id in selected:
        product = products.get(product_id)
        if product is None:
            errors.append(f"{product_id}: product metadata is missing")
            continue
        path: Path | None = None
        if product.cached_asset_id:
            asset = (card.assets or {}).get(product.cached_asset_id)
            if asset is not None and asset.path:
                candidate = asset_path(scene_path, asset)
                if candidate.is_file():
                    path = candidate
        if path is None and product.filename:
            matches = sorted({
                candidate.resolve()
                for root in roots if root.is_dir()
                for candidate in root.rglob(product.filename)
                if candidate.is_file() and candidate.parent.name == "cache"
            })
            if len(matches) == 1:
                path = matches[0]
            elif len(matches) > 1:
                signatures = {(candidate.stat().st_size, _file_digest(candidate)) for candidate in matches}
                if len(signatures) == 1:
                    path = matches[-1]
                else:
                    errors.append(
                        f"{product_id}: multiple nonidentical local files match {product.filename}"
                    )
                    continue
        if path is None:
            errors.append(f"{product_id}: selected FITS is not downloaded locally")
            continue
        found.append(path)
        identities.append(product_id)
    return found, identities, errors


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def product_from_candidate(candidate: CandidateRecord) -> dict[str, object]:
    product: dict[str, object] = {"product_id": candidate.candidate_id, "archive": "MAST"}
    fields = {
        "data_uri": candidate.data_uri, "observation_id": candidate.obs_id or candidate.obsid,
        "mission": candidate.mission, "instrument": candidate.instrument,
        "detector": candidate.detector, "filter": candidate.filter_name,
        "product_type": candidate.product_type, "product_version": candidate.product_version,
        "filename": candidate.product_filename, "exposure_seconds": candidate.exposure_time,
    }
    product.update({key: value for key, value in fields.items() if value is not None})
    return product


def persist_candidate_manifest(
    card: SceneCard, card_path: str | Path, manifest: CandidateManifest,
) -> tuple[SceneCard, Path]:
    """Persist and register a content-addressed discovery snapshot before Apply."""
    scene_path = Path(card_path).resolve()
    if scene_path.name.endswith(".scene.json"):
        root_name = f"{scene_path.name[:-len('.scene.json')]}.assets"
    else:
        root_name = scene_path.stem
    payload = json.dumps(manifest.to_dict(), indent=2).replace("\n", os.linesep).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    asset_id = f"candidate-manifest-{digest[:16]}"
    existing = (card.assets or {}).get(asset_id)
    if existing is not None:
        path = asset_path(scene_path, existing)
        if not path.is_file():
            raise FileNotFoundError(f"candidate manifest asset is missing: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"candidate manifest asset is corrupt: {path}")
    else:
        has_manifest = any(asset.kind == "candidate_manifest" for asset in (card.assets or {}).values())
        filename = "candidates.json" if not has_manifest else f"candidates-{digest[:12]}.json"
        relative = f"{root_name}/inputs/discovery/{filename}"
        path = scene_path.parent / Path(relative)
        write_candidate_manifest(manifest, path)
        data = document(card)
        data.setdefault("assets", {})[asset_id] = document(Asset(
            kind="candidate_manifest", path=relative.replace("\\", "/"),
            media_type="application/json", byte_count=len(payload), sha256=digest,
        ))
        card = SceneCard.model_validate(data)
    data = document(card)
    discovery = dict(data.get("discovery", {}))
    discovery["candidate_manifest_asset_id"] = asset_id
    discovery["archive_retrieved_at"] = manifest.generated_at.replace("+00:00", "Z")
    data["discovery"] = discovery
    return SceneCard.model_validate(data), path


def manifest_from_scene_asset(card: SceneCard, card_path: str | Path) -> CandidateManifest | None:
    asset_id = card.discovery.candidate_manifest_asset_id if card.discovery else None
    if asset_id is None:
        return None
    asset = (card.assets or {}).get(asset_id)
    if asset is None or asset.kind != "candidate_manifest":
        raise ValueError("candidate manifest reference is unresolved")
    path = asset_path(card_path, asset)
    if not path.is_file():
        raise FileNotFoundError(f"candidate manifest asset is missing: {path}")
    payload = path.read_bytes()
    if asset.byte_count is not None and len(payload) != asset.byte_count:
        raise ValueError(f"candidate manifest asset has the wrong size: {path}")
    if asset.sha256 is not None and hashlib.sha256(payload).hexdigest() != asset.sha256.lower():
        raise ValueError(f"candidate manifest asset checksum mismatch: {path}")
    return load_candidate_manifest(path)


def apply_manifest_selection(card: SceneCard, manifest: CandidateManifest) -> SceneCard:
    products: list[dict[str, object]] = []
    for item in manifest.candidates:
        product = product_from_candidate(item)
        cached_asset_id = _local_source_asset_id(card, item.candidate_id, item.product_filename)
        if cached_asset_id is not None:
            product["cached_asset_id"] = cached_asset_id
        products.append(product)
    selected = [item.candidate_id for item in manifest.candidates if item.selected]
    observations = sorted({
        identity for item in manifest.candidates if item.selected
        for identity in [item.obs_id or item.obsid] if identity
    })
    filters = sorted({
        item.filter_name for item in manifest.candidates if item.selected and item.filter_name
    })
    return edit_scene(card, {
        "selection": {"products": products, "selected_product_ids": selected,
                      "observation_ids": observations},
        "planes": {"enabled_filters": filters, "disabled_plane_ids": [],
                   "export_multiplane_fits": True},
    })


def _local_source_asset_id(
    card: SceneCard, product_id: str, filename: str | None,
) -> str | None:
    assets = card.assets or {}
    existing = {
        product.product_id: product.cached_asset_id
        for product in (card.selection.products or [])
    } if card.selection else {}
    existing_id = existing.get(product_id)
    if (
        existing_id is not None
        and existing_id in assets
        and assets[existing_id].kind == "source"
        and assets[existing_id].path is not None
    ):
        return existing_id
    conventional = f"source-{product_id}"
    if (
        conventional in assets
        and assets[conventional].kind == "source"
        and assets[conventional].path is not None
    ):
        return conventional
    if not filename:
        return None
    matches = [
        asset_id for asset_id, asset in assets.items()
        if asset.kind == "source" and asset.path is not None
        and Path(asset.path).name.casefold() == filename.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def manifest_from_card(card: SceneCard) -> CandidateManifest | None:
    if card.selection is None or not card.selection.products:
        return None
    selected = set(card.selection.selected_product_ids or [])
    candidates = [
        CandidateRecord(
            candidate_id=product.product_id, obsid=None, obs_id=product.observation_id,
            product_filename=product.filename, data_uri=product.data_uri,
            mission=product.mission, instrument=product.instrument, detector=product.detector,
            filter_name=product.filter, product_type=product.product_type,
            product_version=product.product_version, observation_date_start=product.observed_at,
            observation_date_end=None, exposure_time=product.exposure_seconds, file_size=None,
            proposal_id=None, proposal_title=None, target_name=card.title,
            selection_rank=[0, 0, [], product.product_id],
            auto_selected=product.product_id in selected,
            auto_selection_reason="selected:saved_scene_pin" if product.product_id in selected
            else "dropped:saved_scene_pin",
            user_selected=product.product_id in selected,
            selected=product.product_id in selected,
            selected_reason="selected:saved_scene_pin" if product.product_id in selected
            else "dropped:saved_scene_pin",
        )
        for product in card.selection.products
    ]
    policy = card.search.observation_selection if card.search and card.search.observation_selection else "all"
    maximum = (
        card.search.max_observations_per_filter
        if card.search and card.search.max_observations_per_filter else 1
    )
    return CandidateManifest(
        generated_at=card.updated_at, config_path=None, selection_policy=policy,
        max_observations_per_filter=maximum, selection_mode="custom",
        candidates=candidates,
    )


def materialize_render_defaults(
    card: SceneCard, *, replace_existing: bool = False,
) -> SceneCard:
    if card.canvas is None:
        card = initialize_canvas(card)
    selected = set(card.selection.selected_product_ids or []) if card.selection else set()
    products = [
        product for product in (card.selection.products or [])
        if product.product_id in selected
    ] if card.selection else []
    filters = sorted({product.filter for product in products if product.filter})
    if not filters:
        raise ValueError("selected products with filter metadata are required")
    changes: dict[str, object] = {}
    if card.planes is None or card.planes.enabled_filters is None:
        changes["planes"] = {"enabled_filters": filters, "disabled_plane_ids": [],
                             "export_multiplane_fits": True}
    if replace_existing or card.mapping is None or not card.mapping.planes:
        weights = recommended_rgb(filters)
        changes["mapping"] = {
            "defaults": {
                "strategy": "continuum",
                "normalization": {
                    "mode": "percentile",
                    "black_percentile": 0.5,
                    "white_percentile": 99.5,
                    "stretch": "asinh",
                    "stretch_parameter": 4.0,
                    "gain": 1.0,
                },
            },
            "planes": [{"filter": name, "rgb": weights[name]} for name in filters],
        }
    if replace_existing or card.tone is None:
        changes["tone"] = {
            "stretch": {channel: {"kind": "asinh", "parameter": 4.0}
                        for channel in ("red", "green", "blue")},
            "percentiles": {"black": 1.0, "white": 99.0},
            "gain": {channel: 1.0 for channel in ("red", "green", "blue")},
            "bias": {channel: 0.0 for channel in ("red", "green", "blue")},
            "saturation": 1.0,
        }
    if replace_existing or card.background is None:
        changes["background"] = {
            "mode": "off",
            "black_reference_policy": "legacy_percentile",
            "inclusion_regions": [],
            "exclusion_regions": [],
            "estimator": {
                "clip_sigma": 3.0,
                "max_iterations": 5,
                "minimum_samples": 256,
                "minimum_valid_fraction": 0.5,
            },
            "resolved_branches": {},
        }
    if replace_existing or card.coverage is None:
        changes["coverage"] = {
            "policy": "available_contributors",
            "tone_reference": "common_required_bands",
            "crop": "none",
            "padding_pixels": 0,
        }
    if card.bridge is None:
        changes["bridge"] = {"enabled": True}
    if replace_existing or card.psf is None:
        changes["psf"] = {"enabled": False}
    return edit_scene(card, changes) if changes else card


def recommended_rgb(filters: list[str]) -> dict[str, dict[str, float]]:
    """Return an explicit, deterministic short-to-blue/long-to-red proposal."""
    unique_filters = list(dict.fromkeys(filters))
    mappings = default_plane_mappings({
        filter_name: {"filter": filter_name} for filter_name in unique_filters
    })
    return {
        entry.plane: entry.rgb.model_dump(mode="json")
        for entry in mappings if entry.plane is not None
    }


def plane_filters_from_card(card: SceneCard) -> dict[str, str]:
    if card.selection is None:
        return {}
    selected = set(card.selection.selected_product_ids or [])
    return {
        product.product_id: product.filter
        for product in card.selection.products or []
        if product.product_id in selected and product.filter
    }


def render_issues(
    card: SceneCard, branch: Literal["original", "deconvolved"] = "original"
) -> list[ReadinessIssue]:
    return readiness(card, "render", plane_filters=plane_filters_from_card(card), branch=branch)


def matching_render(
    card: SceneCard, branch: Literal["original", "deconvolved"] = "original"
):
    for record in reversed(card.renders or []):
        if (record.branch == branch and record.content_revision == card.content_revision
                and effective_inputs(record.inputs) == effective_inputs(card)
                and bridge_snapshot_matches(record.inputs, card)):
            return record
    return None


def merge_render_completion(live: SceneCard, completed: SceneCard) -> SceneCard:
    """Attach completed immutable history without replacing newer live inputs."""
    if live.scene_id != completed.scene_id:
        raise ValueError("render completion belongs to a different scene")
    if completed.content_revision > live.content_revision:
        raise ValueError("render completion is newer than the live scene revision")
    data = document(live)
    live_assets = data.setdefault("assets", {})
    for asset_id, asset in (completed.assets or {}).items():
        payload = document(asset)
        if asset_id in live_assets and live_assets[asset_id] != payload:
            raise ValueError(f"render completion changes registered asset: {asset_id}")
        live_assets[asset_id] = payload
    if not live_assets:
        data.pop("assets")

    def merge_history(field: str, identifier: str) -> None:
        combined: list[dict[str, object]] = []
        by_id: dict[str, dict[str, object]] = {}
        for model in [*(getattr(completed, field) or []), *(getattr(live, field) or [])]:
            payload = document(model)
            item_id = str(payload[identifier])
            if item_id in by_id:
                if by_id[item_id] != payload:
                    raise ValueError(f"render completion changes immutable {field} record: {item_id}")
                continue
            by_id[item_id] = payload
            combined.append(payload)
        if combined:
            data[field] = combined
        else:
            data.pop(field, None)

    merge_history("renders", "render_id")
    merge_history("exports", "export_id")
    if effective_inputs(live) == effective_inputs(completed) and completed.thumbnail_asset_id:
        data["thumbnail_asset_id"] = completed.thumbnail_asset_id
    return SceneCard.model_validate(data)


def resize_canvas(card: SceneCard, width: int, height: int) -> SceneCard:
    canvas_model = card.canvas
    if (canvas_model is None or canvas_model.width is None or canvas_model.height is None
            or canvas_model.pixel_scale_arcsec is None):
        raise ValueError("complete canvas is required")
    if width < 1 or height < 1:
        raise ValueError("output dimensions must be positive")
    if width * canvas_model.height != height * canvas_model.width:
        raise ValueError("output dimensions must preserve the canvas aspect ratio")
    canvas = document(canvas_model)
    canvas["pixel_scale_arcsec"] = canvas_model.pixel_scale_arcsec * canvas_model.width / width
    canvas["width"], canvas["height"] = width, height
    return edit_scene(card, {"canvas": canvas})


def export_current_render(
    card: SceneCard, card_path: str | Path, destination: str | Path, *,
    output_format: Literal["png", "tiff"], overwrite: bool = False,
    branch: Literal["original", "deconvolved"],
) -> SceneCard:
    record = matching_render(card, branch)
    if record is None:
        raise ValueError("a current successful render is required")
    source_id = record.image_asset_id if output_format == "png" else record.high_depth_image_asset_id
    if source_id is None:
        raise ValueError(
            f"current {branch} render does not register a {output_format} output artifact"
        )
    source = asset_path(card_path, (card.assets or {})[source_id])
    target = Path(destination).resolve()
    allowed = {".png"} if output_format == "png" else {".tif", ".tiff"}
    if target.suffix.lower() not in allowed:
        target = target.with_suffix(".png" if output_format == "png" else ".tiff")
    if target.exists() and not overwrite:
        raise FileExistsError(f"export exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copyfile(source, target)
    data = document(card)
    entry = Export(
        export_id=str(uuid4()), render_id=record.render_id, created_at=utc_now(),
        format=output_format, destination=str(target),
    )
    data.setdefault("exports", []).append(document(entry))
    data["output"] = {"format": output_format, "destination_directory": str(target.parent)}
    updated = SceneCard.model_validate(data)
    return save_scene(updated, card_path)

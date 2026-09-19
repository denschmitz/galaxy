"""Scene-card persistence. Local writes are explicit; loading never mutates files."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .scene_models import Asset, Inputs, Render, SceneCard, document, effective_inputs, relative_path
from .scene_readiness import Branch, readiness

logger = logging.getLogger(__name__)
_EXPECTED_UNSET = object()


def validate_scene(data: Any) -> SceneCard:
    """Validate without coercing input; log field-addressed contract violations."""
    try:
        return SceneCard.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            path = ".".join(str(part) for part in error["loc"]) or "$"
            logger.error("%s: [%s] %s", path, error["type"], error["msg"])
        raise


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def create_scene(title: str = "Untitled scene", *, now: str | None = None) -> SceneCard:
    timestamp = now if now is not None else utc_now()
    return SceneCard.model_validate({
        "document_type": "galaxy.scene_card", "schema_version": 1, "scene_id": str(uuid4()),
        "title": title, "created_at": timestamp, "updated_at": timestamp, "content_revision": 1,
    })


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def load_scene(path: str | Path) -> SceneCard:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError) as exc:
        logger.error("$: [invalid_json] %s", exc)
        raise
    return validate_scene(data)


def asset_path(card_path: str | Path, asset: Asset) -> Path:
    if asset.path is None:
        raise ValueError("URI-backed asset has no local path")
    relative_path(asset.path)
    root = Path(card_path).resolve().parent
    resolved = root.joinpath(*asset.path.replace("\\", "/").split("/")).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"asset path escapes card directory: {asset.path}")
    return resolved


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    asset_id: str
    code: str
    message: str


def dependency_issues(card: SceneCard, path: str | Path) -> list[DependencyIssue]:
    """Report missing/corrupt local assets without changing or rejecting the card."""
    card = SceneCard.model_validate(document(card))
    issues: list[DependencyIssue] = []
    for aid, asset in (card.assets or {}).items():
        if asset.path is None:
            continue
        try:
            binary = asset_path(path, asset)
            if not binary.is_file():
                issues.append(DependencyIssue(aid, "missing", str(binary)))
                continue
            _verify_bytes(asset, binary.read_bytes())
        except (OSError, ValueError) as exc:
            issues.append(DependencyIssue(aid, "invalid", str(exc)))
    return issues


def _verify_bytes(asset: Asset, content: bytes) -> None:
    if asset.byte_count is not None and len(content) != asset.byte_count:
        raise ValueError("asset byte_count mismatch")
    if asset.sha256 is not None and hashlib.sha256(content).hexdigest() != asset.sha256.lower():
        raise ValueError("asset sha256 mismatch")


def edit_scene(card: SceneCard, changes: Mapping[str, Any], *, remove: tuple[str, ...] = ()) -> SceneCard:
    """Replace named top-level working fields; nested replacement is deliberate."""
    protected = {"document_type", "schema_version", "scene_id", "created_at", "updated_at",
                 "content_revision", "renders", "exports", "assets"}
    if protected & (set(changes) | set(remove)):
        raise ValueError("identity, timestamps, assets and history are not editable settings")
    if set(changes) & set(remove):
        raise ValueError("cannot both replace and remove the same field")
    original = SceneCard.model_validate(document(card))
    data = document(original)
    for key in remove:
        if key not in SceneCard.model_fields:
            raise ValueError(f"unknown field: {key}")
        data.pop(key, None)
    data.update(changes)
    # Clear a generated thumbnail before validating a potentially changed revision.
    thumbnail = data.pop("thumbnail_asset_id", None)
    data["content_revision"] += 1
    candidate = SceneCard.model_validate(data)
    changed = effective_inputs(candidate) != effective_inputs(original)
    if not changed:
        data["content_revision"] -= 1
    if thumbnail and (not changed or (original.assets or {})[thumbnail].kind == "discovery_thumbnail"):
        data["thumbnail_asset_id"] = thumbnail
    return SceneCard.model_validate(data)


def _check_update(previous: SceneCard, current: SceneCard) -> None:
    for key in ("scene_id", "created_at", "document_type", "schema_version"):
        if getattr(previous, key) != getattr(current, key):
            raise ValueError(f"cannot overwrite different scene identity: {key}")
    if current.content_revision < previous.content_revision:
        raise ValueError("cannot save an older content revision")
    if effective_inputs(previous) != effective_inputs(current) and current.content_revision <= previous.content_revision:
        raise ValueError("changed inputs require a new content revision")
    for field in ("renders", "exports"):
        before = document(previous).get(field, [])
        after = document(current).get(field, [])
        if after[:len(before)] != before:
            raise ValueError(f"{field} history is append-only and immutable")
    for aid, asset in (previous.assets or {}).items():
        if (current.assets or {}).get(aid) != asset:
            raise ValueError(f"registered asset is immutable: {aid}")


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    """Replace only after complete UTF-8 serialization and fsync."""
    encoded = (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_scene(
    card: SceneCard, path: str | Path, *, asset_contents: Mapping[str, bytes] | None = None,
    now: str | None = None, expected_previous: SceneCard | None | object = _EXPECTED_UNSET,
) -> SceneCard:
    """Commit binaries before JSON. Never replace existing asset bytes.

    New local references must exist; previously registered missing dependencies
    remain recoverable, so metadata-only saves do not discard them.
    """
    current = validate_scene(document(card))
    destination = Path(path).resolve()
    previous = load_scene(destination) if destination.exists() else None
    if expected_previous is not _EXPECTED_UNSET:
        expected_document = (
            None
            if expected_previous is None
            else document(SceneCard.model_validate(document(expected_previous)))
        )
        actual_document = None if previous is None else document(previous)
        if actual_document != expected_document:
            raise ValueError("scene changed since it was read; reload before saving")
    if previous is not None:
        _check_update(previous, current)
    data = document(current)
    timestamp = now if now is not None else utc_now()
    if previous is not None and datetime.fromisoformat(timestamp) < datetime.fromisoformat(previous.updated_at):
        raise ValueError("save timestamp cannot precede the previous save")
    data["updated_at"] = timestamp
    committed = SceneCard.model_validate(data)
    assets = committed.assets or {}
    contents = asset_contents or {}
    if set(contents) - set(assets):
        raise ValueError("asset_contents contains an unregistered asset ID")
    paths: dict[str, Path] = {}
    for aid, asset in assets.items():
        if asset.path is not None:
            paths[aid] = asset_path(destination, asset)
            if paths[aid] == destination:
                raise ValueError("asset cannot refer to the scene JSON itself")
        elif aid in contents:
            raise ValueError("cannot write bytes to URI-backed asset")
    if len(set(paths.values())) != len(paths):
        raise ValueError("different asset IDs cannot alias the same local path")
    # Validate all payloads before beginning any writes.
    for aid, payload in contents.items():
        if not isinstance(payload, bytes):
            raise TypeError("asset_contents values must be bytes")
        _verify_bytes(assets[aid], payload)
        if paths[aid].exists() and paths[aid].read_bytes() != payload:
            raise ValueError(f"refusing to overwrite immutable asset: {aid}")
    old_assets = (previous.assets or {}) if previous else {}
    for aid, binary in paths.items():
        if aid not in old_assets and aid not in contents:
            if not binary.is_file():
                raise ValueError(f"new asset must be complete before save: {aid}")
            _verify_bytes(assets[aid], binary.read_bytes())
    # Newly appended history must not point at missing old assets either.
    old_render_ids = {r.render_id for r in previous.renders or []} if previous else set()
    new_history_assets: set[str] = set()
    for record in committed.renders or []:
        if record.render_id not in old_render_ids:
            new_history_assets.update([record.image_asset_id, record.provenance_asset_id])
            new_history_assets.update(record.aligned_plane_asset_ids or [])
            new_history_assets.update(x for x in (record.thumbnail_asset_id, record.footprint_asset_id) if x)
    old_export_ids = {e.export_id for e in previous.exports or []} if previous else set()
    new_history_assets.update(e.asset_id for e in committed.exports or []
                              if e.export_id not in old_export_ids and e.asset_id)
    for aid in new_history_assets:
        if aid in paths and aid not in contents:
            if not paths[aid].is_file():
                raise ValueError(f"completed history requires available binary: {aid}")
            _verify_bytes(assets[aid], paths[aid].read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)
    for aid, payload in contents.items():
        binary = paths[aid]
        if binary.exists():
            continue
        binary.parent.mkdir(parents=True, exist_ok=True)
        try:
            with binary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if binary.read_bytes() != payload:
                raise ValueError(f"asset created concurrently with different bytes: {aid}")
    _atomic_json(destination, document(committed))
    return committed


def append_render(
    card: SceneCard, *, snapshot: SceneCard, branch: Branch, plane_filters: Mapping[str, str],
    image_asset_id: str, provenance_asset_id: str, assets: Mapping[str, Asset],
    thumbnail_asset_id: str | None = None, now: str | None = None,
) -> SceneCard:
    """Attach a successful completed run using its frozen launch-time card.

    This records success supplied by the caller; the processing layer must only
    call this after successful completion. save_scene verifies local binaries.
    """
    card = SceneCard.model_validate(document(card))
    snapshot = SceneCard.model_validate(document(snapshot))
    if card.scene_id != snapshot.scene_id or snapshot.content_revision > card.content_revision:
        raise ValueError("render snapshot must belong to this scene and an existing revision")
    if snapshot.content_revision == card.content_revision and effective_inputs(snapshot) != effective_inputs(card):
        raise ValueError("same revision cannot represent different inputs")
    problems = readiness(snapshot, "render", plane_filters=plane_filters, branch=branch)
    if problems:
        raise ValueError("\n".join(f"{p.path}: {p.message}" for p in problems))
    data = document(card)
    merged = dict(data.get("assets", {}))
    for aid, asset in assets.items():
        validated = Asset.model_validate(document(asset))
        if aid in merged and merged[aid] != document(validated):
            raise ValueError(f"asset ID already registered: {aid}")
        merged[aid] = document(validated)
    data["assets"] = merged
    record_data: dict[str, Any] = {
        "render_id": str(uuid4()), "created_at": now if now is not None else utc_now(),
        "content_revision": snapshot.content_revision, "branch": branch,
        "image_asset_id": image_asset_id, "provenance_asset_id": provenance_asset_id,
        "inputs": effective_inputs(snapshot),
    }
    if thumbnail_asset_id:
        record_data["thumbnail_asset_id"] = thumbnail_asset_id
    record = Render.model_validate(record_data)
    data.setdefault("renders", []).append(document(record))
    if thumbnail_asset_id and snapshot.content_revision == card.content_revision:
        data["thumbnail_asset_id"] = thumbnail_asset_id
    return SceneCard.model_validate(data)


def duplicate_scene(
    card: SceneCard, source_path: str | Path, destination_path: str | Path, *,
    title: str | None = None, now: str | None = None,
) -> SceneCard:
    """Save a new identity with independent local working assets and no history."""
    original = SceneCard.model_validate(document(card))
    destination = Path(destination_path).resolve()
    if destination.exists() or destination == Path(source_path).resolve():
        raise ValueError("duplicate destination must be a new file")
    data = document(original)
    fresh = document(create_scene(original.title if title is None else title, now=now))
    data.update(fresh)
    data.pop("renders", None)
    data.pop("exports", None)
    thumbnail = data.pop("thumbnail_asset_id", None)
    retained: dict[str, Any] = {}
    contents: dict[str, bytes] = {}
    kinds = {"source", "discovery_thumbnail", "candidate_manifest", "psf_kernel"}
    folder = f"{destination.stem}.{fresh['scene_id']}.assets"
    for aid, asset in (original.assets or {}).items():
        if asset.kind not in kinds:
            continue
        entry = document(asset)
        if asset.path is not None:
            binary = asset_path(source_path, asset)
            content = binary.read_bytes()
            _verify_bytes(asset, content)
            entry["path"] = f"{folder}/{hashlib.sha256(aid.encode()).hexdigest()}{binary.suffix}"
            contents[aid] = content
        retained[aid] = entry
    if retained or "assets" in data:
        data["assets"] = retained
    if thumbnail in retained and retained[thumbnail]["kind"] == "discovery_thumbnail":
        data["thumbnail_asset_id"] = thumbnail
    duplicate = SceneCard.model_validate(data)
    return save_scene(duplicate, destination, asset_contents=contents, now=now)


def duplicate_scene_draft(
    card: SceneCard, *, title: str | None = None, now: str | None = None
) -> SceneCard:
    """Create an unsaved independent identity while retaining reusable input assets."""
    original = SceneCard.model_validate(document(card))
    data = document(original)
    fresh = document(create_scene(original.title if title is None else title, now=now))
    data.update(fresh)
    data.pop("renders", None)
    data.pop("exports", None)
    data.pop("output", None)
    thumbnail = data.pop("thumbnail_asset_id", None)
    reusable = {"source", "discovery_thumbnail", "candidate_manifest", "psf_kernel"}
    data["assets"] = {
        aid: document(asset) for aid, asset in (original.assets or {}).items()
        if asset.kind in reusable
    }
    if not data["assets"]:
        data.pop("assets")
    if thumbnail and thumbnail in data.get("assets", {}):
        data["thumbnail_asset_id"] = thumbnail
    return SceneCard.model_validate(data)

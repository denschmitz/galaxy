"""Persist and classify MAST candidate results by canonical scene query inputs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .scene_models import SceneCard, document
from .selection import CandidateManifest, load_candidate_manifest, write_candidate_manifest


DEFAULT_MAX_AGE = timedelta(days=183)


@dataclass(frozen=True, slots=True)
class CachedCandidateResult:
    manifest: CandidateManifest
    path: Path
    retrieved_at: datetime
    stale: bool


def candidate_cache_path(cache_directory: str | Path, card: SceneCard) -> Path:
    query = {
        "target": document(card.target) if card.target is not None else None,
        "search": document(card.search) if card.search is not None else None,
    }
    encoded = json.dumps(query, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return Path(cache_directory).resolve() / f"{hashlib.sha256(encoded).hexdigest()}.candidates.json"


def load_cached_candidates(
    cache_directory: str | Path,
    card: SceneCard,
    *,
    now: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> CachedCandidateResult | None:
    path = candidate_cache_path(cache_directory, card)
    if not path.is_file():
        return None
    manifest = load_candidate_manifest(path)
    retrieved_at = datetime.fromisoformat(manifest.generated_at.replace("Z", "+00:00"))
    if retrieved_at.tzinfo is None:
        raise ValueError(f"cached candidate timestamp has no timezone: {path}")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("cache comparison time must include a timezone")
    return CachedCandidateResult(
        manifest, path, retrieved_at, current.astimezone(timezone.utc) - retrieved_at > max_age
    )


def save_cached_candidates(
    cache_directory: str | Path, card: SceneCard, manifest: CandidateManifest
) -> CachedCandidateResult:
    path = candidate_cache_path(cache_directory, card)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_candidate_manifest(manifest, path)
    loaded = load_cached_candidates(path.parent, card)
    if loaded is None:
        raise OSError(f"candidate cache publication failed: {path}")
    return loaded

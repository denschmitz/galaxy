from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ArtifactBranch = Literal["original", "deconvolved"]


@dataclass(frozen=True, slots=True)
class BranchArtifactPaths:
    """Canonical durable paths for one immutable render branch."""

    branch: ArtifactBranch
    directory: Path
    aligned_directory: Path
    aligned_planes: Path
    checkpoint_manifest: Path
    composite_png: Path
    composite_tiff: Path
    thumbnail_png: Path
    background_diagnostics: Path
    background_overlay: Path


def branch_artifact_paths(run_directory: str | Path, branch: ArtifactBranch) -> BranchArtifactPaths:
    root = Path(run_directory)
    directory = root / branch
    return BranchArtifactPaths(
        branch=branch,
        directory=directory,
        aligned_directory=directory / "aligned",
        aligned_planes=directory / "aligned-planes.fits",
        checkpoint_manifest=directory / "aligned-checkpoint.json",
        composite_png=directory / "composite.png",
        composite_tiff=directory / "composite.tiff",
        thumbnail_png=directory / "thumbnail.png",
        background_diagnostics=directory / "background-diagnostics.json",
        background_overlay=directory / "background-regions.png",
    )


def existing_branch_artifact_paths(
    run_directory: str | Path, branch: ArtifactBranch,
) -> BranchArtifactPaths | None:
    """Resolve canonical output first, then the read-only legacy flat layout."""
    canonical = branch_artifact_paths(run_directory, branch)
    if canonical.aligned_planes.is_file():
        return canonical

    root = Path(run_directory)
    suffix = "" if branch == "original" else "_deconvolved"
    legacy_planes = root / f"exported_planes{suffix}.fits"
    if not legacy_planes.is_file():
        return None
    return BranchArtifactPaths(
        branch=branch,
        directory=root,
        aligned_directory=root / "reprojected" / branch,
        aligned_planes=legacy_planes,
        checkpoint_manifest=legacy_planes.with_suffix(".checkpoint.json"),
        composite_png=root / f"composite{suffix}.png",
        composite_tiff=root / f"composite{suffix}.tiff",
        thumbnail_png=root / f"thumbnail{suffix}.png",
        background_diagnostics=root / f"background_diagnostics{suffix}.json",
        background_overlay=root / f"background_regions{suffix}.png",
    )

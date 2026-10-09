from pathlib import Path

from galaxy.artifact_paths import branch_artifact_paths, existing_branch_artifact_paths


def test_canonical_branch_paths_are_separate_and_bounded(tmp_path: Path) -> None:
    original = branch_artifact_paths(tmp_path, "original")
    deconvolved = branch_artifact_paths(tmp_path, "deconvolved")

    assert original.aligned_planes == tmp_path / "original" / "aligned-planes.fits"
    assert original.checkpoint_manifest == tmp_path / "original" / "aligned-checkpoint.json"
    assert original.aligned_directory == tmp_path / "original" / "aligned"
    assert deconvolved.composite_tiff == tmp_path / "deconvolved" / "composite.tiff"
    assert original.directory != deconvolved.directory
    assert all(tmp_path in path.parents for path in (
        original.aligned_planes,
        original.checkpoint_manifest,
        original.composite_png,
        original.composite_tiff,
        deconvolved.aligned_planes,
    ))


def test_existing_branch_paths_prefer_canonical_over_legacy(tmp_path: Path) -> None:
    legacy = tmp_path / "exported_planes.fits"
    legacy.touch()
    canonical = branch_artifact_paths(tmp_path, "original")
    canonical.aligned_planes.parent.mkdir(parents=True)
    canonical.aligned_planes.touch()

    resolved = existing_branch_artifact_paths(tmp_path, "original")

    assert resolved == canonical


def test_existing_branch_paths_support_legacy_without_moving_it(tmp_path: Path) -> None:
    legacy = tmp_path / "exported_planes_deconvolved.fits"
    legacy.touch()

    resolved = existing_branch_artifact_paths(tmp_path, "deconvolved")

    assert resolved is not None
    assert resolved.aligned_planes == legacy
    assert resolved.checkpoint_manifest == tmp_path / "exported_planes_deconvolved.checkpoint.json"
    assert legacy.exists()

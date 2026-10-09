from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from galaxy.scene_card import create_scene, save_scene
from galaxy.scene_workflow import (
    LibraryEntry, LibraryOrigin, associated_asset_root, delete_library_scene,
    list_scene_library,
)


def _saved_project(scene_directory: Path) -> LibraryEntry:
    scene_directory.mkdir(parents=True, exist_ok=True)
    path = scene_directory / "horsehead-12345678.scene.json"
    save_scene(create_scene("Horsehead Nebula"), path)
    root = associated_asset_root(path)
    root.mkdir()
    (root / "preview.png").write_bytes(b"preview")
    return list_scene_library(scene_directory)[0]


def test_delete_project_moves_only_card_and_associated_asset_root(tmp_path: Path) -> None:
    entry = _saved_project(tmp_path)
    root = associated_asset_root(entry.path)
    cache = tmp_path / "discovery-cache.json"
    cache.write_text("cache", encoding="utf-8")
    external = tmp_path / "exports" / "external.png"
    external.parent.mkdir()
    external.write_bytes(b"external")

    deleted = delete_library_scene(entry, tmp_path, transaction_id="delete-1")

    assert not entry.path.exists()
    assert not root.exists()
    assert (deleted.recovery_directory / entry.path.name).is_file()
    assert (deleted.recovery_directory / root.name / "preview.png").read_bytes() == b"preview"
    manifest = json.loads((deleted.recovery_directory / "recovery.json").read_text())
    assert manifest["scene_id"] == entry.card.scene_id
    assert {item["original_path"] for item in manifest["members"]} == {
        str(entry.path), str(root),
    }
    assert cache.read_text(encoding="utf-8") == "cache"
    assert external.read_bytes() == b"external"


def test_delete_project_rolls_back_when_second_move_fails(tmp_path: Path) -> None:
    entry = _saved_project(tmp_path)
    root = associated_asset_root(entry.path)
    calls = 0

    def fail_second_move(source: str | Path, destination: str | Path) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected failure")
        return os.replace(source, destination)

    with pytest.raises(OSError, match="rolled back"):
        delete_library_scene(entry, tmp_path, move=fail_second_move, transaction_id="delete-2")

    assert entry.path.is_file()
    assert (root / "preview.png").is_file()
    assert not (tmp_path / ".galaxy-trash" / "delete-2").exists()


def test_delete_project_rejects_bundled_example(tmp_path: Path) -> None:
    entry = _saved_project(tmp_path)
    example = LibraryEntry(
        path=entry.path, card=entry.card, error=None,
        origin=LibraryOrigin.BUNDLED_EXAMPLE,
    )

    with pytest.raises(ValueError, match="bundled examples"):
        delete_library_scene(example, tmp_path)

    assert entry.path.is_file()
    assert associated_asset_root(entry.path).is_dir()

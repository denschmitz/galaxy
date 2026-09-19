from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence


CONFIG_FILENAME = "galaxy.config.json"
DEFAULT_SCENE_DIRECTORY = "artifacts/scenes"


class ApplicationConfigError(ValueError):
    """Application startup could not resolve valid local settings."""


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    project_root: Path
    config_path: Path
    scene_directory: Path


def find_project_root() -> Path:
    """Locate the source checkout, independently of the launch directory."""
    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file() or not (root / "src" / "galaxy").is_dir():
        raise ApplicationConfigError(f"Cannot locate Galaxy source checkout at {root}")
    return root


def _path_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ApplicationConfigError(f"{label}: expected a nonblank path string")
    return value


def _resolve_directory(value: str, base: Path, label: str) -> Path:
    try:
        path = Path(value)
        result = (path if path.is_absolute() else base / path).resolve()
        if result.exists() and not result.is_dir():
            raise ApplicationConfigError(f"{label}: not a directory: {result}")
        return result
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ApplicationConfigError):
            raise
        raise ApplicationConfigError(f"{label}: cannot resolve {value!r}: {exc}") from exc


def load_application_settings(
    scene_directory_override: str | None = None,
    *,
    project_root: Path | None = None,
    working_directory: Path | None = None,
) -> ApplicationSettings:
    root = (project_root if project_root is not None else find_project_root()).resolve()
    cwd = (working_directory if working_directory is not None else Path.cwd()).resolve()
    config_path = root / CONFIG_FILENAME
    # Exclusive creation preserves existing preferences, including concurrent creation.
    try:
        with config_path.open("x", encoding="utf-8") as stream:
            json.dump({"scene_directory": DEFAULT_SCENE_DIRECTORY}, stream, indent=2)
            stream.write("\n")
    except FileExistsError:
        pass
    except OSError as exc:
        raise ApplicationConfigError(f"Cannot create {config_path}: {exc}") from exc

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApplicationConfigError(f"Cannot read {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApplicationConfigError(f"{config_path}: expected a JSON object")
    configured = _path_value(
        payload.get("scene_directory", DEFAULT_SCENE_DIRECTORY),
        f"{config_path}: scene_directory",
    )
    # Validate a supplied setting even when an override has higher precedence.
    if scene_directory_override is None:
        effective = _resolve_directory(configured, root, f"{config_path}: scene_directory")
    else:
        override = _path_value(scene_directory_override, "--scene-dir")
        effective = _resolve_directory(override, cwd, "--scene-dir")
    return ApplicationSettings(root, config_path, effective)


def parse_ui_startup_args(argv: Sequence[str]) -> tuple[str | None, list[str]]:
    """Consume application options without mistaking their values for input files."""
    parser = argparse.ArgumentParser(prog="galaxy-ui", allow_abbrev=False)
    parser.add_argument("--scene-dir")
    args, remaining = parser.parse_known_args(list(argv))
    return args.scene_dir, remaining

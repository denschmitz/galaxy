from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any

import pytest

from galaxy.app_config import (
    ApplicationConfigError,
    ApplicationSettings,
    find_project_root,
    load_application_settings,
    parse_ui_startup_args,
)


def test_missing_config_creates_default_independent_of_cwd(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    result = load_application_settings(project_root=root, working_directory=cwd)
    assert json.loads(result.config_path.read_text()) == {"scene_directory": "artifacts/scenes"}
    assert result.scene_directory == root / "artifacts" / "scenes"
    assert not (cwd / "galaxy.config.json").exists()


@pytest.mark.parametrize("payload", [{}, {"scene_directory": "custom library"}])
def test_existing_config_is_preserved(tmp_path: Path, payload: dict[str, str]) -> None:
    config = tmp_path / "galaxy.config.json"
    original = json.dumps(payload, separators=(",", ":")).encode()
    config.write_bytes(original)
    result = load_application_settings(project_root=tmp_path)
    assert config.read_bytes() == original
    assert result.scene_directory == tmp_path / payload.get("scene_directory", "artifacts/scenes")


def test_override_wins_and_still_initializes_default(tmp_path: Path) -> None:
    cwd = tmp_path / "working"
    cwd.mkdir()
    result = load_application_settings("alternate", project_root=tmp_path, working_directory=cwd)
    assert result.scene_directory == cwd / "alternate"
    assert json.loads(result.config_path.read_text()) == {"scene_directory": "artifacts/scenes"}
    second = load_application_settings(project_root=tmp_path, working_directory=cwd)
    assert second.scene_directory == tmp_path / "artifacts" / "scenes"


def test_absolute_config_and_override(tmp_path: Path) -> None:
    config = tmp_path / "galaxy.config.json"
    configured = tmp_path / "configured"
    overridden = tmp_path / "override"
    config.write_text(json.dumps({"scene_directory": str(configured)}))
    before = config.read_bytes()
    assert load_application_settings(project_root=tmp_path).scene_directory == configured
    assert load_application_settings(str(overridden), project_root=tmp_path).scene_directory == overridden
    assert config.read_bytes() == before


@pytest.mark.parametrize("contents", ["{", "[]", "null", '"string"', '{"scene_directory":null}',
                                      '{"scene_directory":3}', '{"scene_directory":false}',
                                      '{"scene_directory":""}', '{"scene_directory":"  "}'])
def test_invalid_config_is_not_silently_replaced(tmp_path: Path, contents: str) -> None:
    config = tmp_path / "galaxy.config.json"
    config.write_text(contents)
    with pytest.raises(ApplicationConfigError, match="galaxy.config.json"):
        load_application_settings("override", project_root=tmp_path)
    assert config.read_text() == contents


@pytest.mark.parametrize("value", ["", " ", "\x00"])
def test_invalid_override_is_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(ApplicationConfigError, match="--scene-dir"):
        load_application_settings(value, project_root=tmp_path)


def test_selected_path_must_not_be_existing_file(tmp_path: Path) -> None:
    invalid = tmp_path / "file"
    invalid.write_text("data")
    with pytest.raises(ApplicationConfigError, match="not a directory"):
        load_application_settings(str(invalid), project_root=tmp_path)


def test_creation_failure_has_path_and_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.open
    def failing_open(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        if path.name == "galaxy.config.json" and mode == "x":
            raise PermissionError("creation denied")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(ApplicationConfigError, match="Cannot create .*galaxy.config.json"):
        load_application_settings(project_root=tmp_path)


def test_read_failure_has_path_and_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "galaxy.config.json"
    config.write_text("{}")
    original = Path.read_text
    def failing_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == config:
            raise PermissionError("read denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", failing_read)
    with pytest.raises(ApplicationConfigError, match="Cannot read .*galaxy.config.json"):
        load_application_settings(project_root=tmp_path)


def test_ui_option_value_is_not_an_input_path() -> None:
    override, remaining = parse_ui_startup_args(["--scene-dir", "library", "input.json"])
    assert override == "library"
    assert remaining == ["input.json"]


def test_missing_ui_override_argument_fails() -> None:
    with pytest.raises(SystemExit) as error:
        parse_ui_startup_args(["--scene-dir"])
    assert error.value.code == 2


def test_root_is_based_on_module_not_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    assert find_project_root() == expected


@pytest.mark.parametrize("args", [
    ["--scene-dir", "chosen", "validate-scene", "--scene", "input.scene.json"],
    ["validate-scene", "--scene", "input.scene.json", "--scene-dir", "chosen"],
])
def test_cli_initializes_shared_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        args: list[str]) -> None:
    from galaxy import cli
    captured = []
    def initialize(override: str | None) -> ApplicationSettings:
        settings = load_application_settings(override, project_root=tmp_path, working_directory=tmp_path)
        captured.append(settings)
        return settings
    monkeypatch.setattr(cli, "load_application_settings", initialize)
    monkeypatch.setattr(cli, "load_scene", lambda path: object())
    monkeypatch.setattr(cli, "_configure_initial_logging", lambda args: None)
    assert cli.main(args) == 0
    assert captured[0].scene_directory == tmp_path / "chosen"


def test_cli_config_error_stops_before_project_loading(tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from galaxy import cli
    (tmp_path / "galaxy.config.json").write_text("[]")
    monkeypatch.setattr(cli, "load_application_settings",
                        lambda override: load_application_settings(override, project_root=tmp_path))
    def unexpected_load(path: str) -> None:
        pytest.fail("Project must not load after application configuration failure")
    monkeypatch.setattr(cli, "load_scene", unexpected_load)
    with pytest.raises(SystemExit) as error:
        cli.main(["validate-scene", "--scene", "input.scene.json"])
    assert error.value.code == 2


def test_ui_uses_shared_settings_and_consumed_args(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from galaxy import ui
    captured = []
    state = {}
    monkeypatch.setattr(ui, "st", SimpleNamespace(
        set_page_config=lambda **kwargs: None, session_state=state, error=lambda message: None))
    monkeypatch.setattr(ui.sys, "argv", ["ui.py", "--scene-dir", "library", "input.json"])
    monkeypatch.setattr(ui, "load_application_settings",
                        lambda override: load_application_settings(override, project_root=tmp_path,
                                                                   working_directory=tmp_path))
    def resolve(args: list[str]) -> None:
        captured.append(args)
        return None
    monkeypatch.setattr(ui, "_explicit_input", resolve)
    monkeypatch.setattr(ui, "_initialize_session", lambda settings, path: None)
    monkeypatch.setattr(ui, "_render_app", lambda settings: None)
    ui.main()
    assert captured == [["input.json"]]
    assert state["application_settings"].scene_directory == tmp_path / "library"


def test_ui_config_error_stops_before_input_resolution(tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from galaxy import ui
    (tmp_path / "galaxy.config.json").write_text("[]")
    errors = []
    monkeypatch.setattr(ui, "st", SimpleNamespace(
        set_page_config=lambda **kwargs: None, session_state={}, error=errors.append))
    monkeypatch.setattr(ui.sys, "argv", ["ui.py"])
    monkeypatch.setattr(ui, "load_application_settings",
                        lambda override: load_application_settings(override, project_root=tmp_path))
    def unexpected_resolve(args: list[str]) -> None:
        pytest.fail("Input resolution must not run after configuration failure")
    monkeypatch.setattr(ui, "_explicit_input", unexpected_resolve)
    ui.main()
    assert len(errors) == 1
    assert "galaxy.config.json" in errors[0]

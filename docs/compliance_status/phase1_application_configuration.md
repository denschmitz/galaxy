# Phase 1: Application Configuration

Status: applied to the local project and verified with its .venv interpreter.

## Phase 1A â€” Baseline and requirements

Reviewed REQ-CONFIG-001 through REQ-CONFIG-010, REQ-CLI-004, and GAP-CONFIG-001. Preserve the existing YAML scene implementation until its separately planned translation is complete. Keep application preferences distinct from scene settings.

## Phase 1B â€” Implementation

- Added immutable ApplicationSettings and a shared application configuration loader.
- Create missing project-root galaxy.config.json using exclusive creation with scene_directory=artifacts/scenes.
- Validate the configuration and resolve CLI > configuration > default precedence.
- Base configured relative paths on the project root and CLI relative paths on startup working directory.
- Preserve existing config bytes; never save CLI overrides.
- Integrate startup into CLI and UI. Consume UI option arguments before resolving input artifacts.
- Supply a committed example config and ignore local galaxy.config.json.
- Retain resolved settings in the CLI invocation and UI session for later scene-library consumers.

## Phase 1C â€” Verification and closeout

The staged implementation was applied to the local project. Running .venv/Scripts/python.exe -m pytest tests/test_app_config.py tests/test_cli.py tests/test_ui.py -q locally produced 49 passed and 1 pre-existing failure. Pytest also reported that its .pytest_cache directory was not writable; this did not prevent test execution.

The failure is tests/test_ui.py::test_load_or_query_discovery_manifest_uses_disk_cache. Its fixed 2026-01-01 timestamp is older than the cache freshness limit, but the test expects reuse without refresh. Running the same test with untouched repository source reproduced the failure. It was not bypassed or changed.

A focused staged run of the configuration and CLI tests passed all 32 tests; the local combined run also passed these tests.

Phase 1 startup/configuration code is now applied locally. REQ-CONFIG-010 remains partially integrated: the effective location is available to both entrypoints; Saved scenes and JSON scene save routing belong to the later UI/storage phases. GAP-CONFIG-001 remains open only for downstream integration. No Git commit or push was performed.

## Usage after applying

Configuration: project-root galaxy.config.json, with {"scene_directory":"artifacts/scenes"} by default.

CLI examples:
- python -m galaxy.cli --scene-dir alternate validate-scene --scene examples/pillars.scene.json
- python -m galaxy.cli validate-scene --scene examples/pillars.scene.json --scene-dir alternate

UI example:
- python -m streamlit run src/galaxy/ui.py -- --scene-dir alternate artifacts/pillars/exported_planes.fits

Legacy YAML arguments in these examples reflect the current runtime; the approved one-time migration and JSON-only cutover are separate phases. --scene-dir does not replace --workdir or move existing scene files.

## Remaining gaps

- Local patch application is complete; the standard editor required a scoped command-runner fallback for the workspace junction.
- GAP-CONFIG-001: downstream library/new-scene save consumers not yet implemented.
- Existing cache test needs a deterministic injected clock/freshness fixture in its owning phase.

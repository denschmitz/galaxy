# Application Configuration Coverage

Scope: application startup and configured scene-directory consumers through Phase 5.

| Requirement | Implementation | Verification |
| --- | --- | --- |
| REQ-CONFIG-001 | app_config.load_application_settings; CLI/UI startup | test_cli_initializes_shared_settings; test_ui_uses_shared_settings_and_consumed_args |
| REQ-CONFIG-002 | DEFAULT_SCENE_DIRECTORY | test_missing_config_creates_default_independent_of_cwd; test_existing_config_is_preserved |
| REQ-CONFIG-003 | exclusive config creation | test_override_wins_and_still_initializes_default |
| REQ-CONFIG-004 | existing-file load without rewrite | test_existing_config_is_preserved; test_absolute_config_and_override |
| REQ-CONFIG-005 | shared loader precedence | test_override_wins_and_still_initializes_default; test_absolute_config_and_override |
| REQ-CONFIG-006 | configured path resolution | test_existing_config_is_preserved; test_missing_config_creates_default_independent_of_cwd |
| REQ-CONFIG-007 | CLI path resolution against startup cwd | test_override_wins_and_still_initializes_default |
| REQ-CONFIG-008 | explicit payload/path validation | test_invalid_config_is_not_silently_replaced; test_invalid_override_is_rejected |
| REQ-CONFIG-009 | startup error diagnostics | test_creation_failure_has_path_and_operation; test_read_failure_has_path_and_operation; test_cli_config_error_stops_before_project_loading; test_ui_config_error_stops_before_input_resolution |
| REQ-CONFIG-010 | settings supplied to CLI/UI, scene library, and new-scene saves | Covered by startup, save routing, and library tests |
| REQ-CLI-004 | global/subcommand parser and UI option parser | test_cli_initializes_shared_settings; test_ui_option_value_is_not_an_input_path; test_missing_ui_override_argument_fails |

Implementation file: src/galaxy/app_config.py, with consumers in src/galaxy/cli.py and src/galaxy/ui.py.
Test file: tests/test_app_config.py.
Regression files: tests/test_cli.py and tests/test_ui.py.

# Phase 3 Scene-Card Execution Coverage

## Scope

This matrix covers the JSON scene-card execution seam, exact product pinning, inspected-plane validation, native-frame PSF ordering, CLI cutover, render-history commit, and safe-boundary cancellation.

| Requirement | Implementation | Tests | Status |
| --- | --- | --- | --- |
| REQ-EXEC-001 | `scene_execution.py`; `pipeline.py` pinned selection path | `test_scene_pipeline_uses_local_pin_records_history_and_writes_no_yaml` | Covered |
| REQ-EXEC-002, REQ-IFACE-004, REQ-IFACE-005 | `prepare_scene_execution`; `_local_product_manifest` | local-pin, missing-pin, exact-candidate assertions | Covered |
| REQ-EXEC-003, REQ-PROJ-015 through REQ-PROJ-018 | `scene_readiness.py`; `pipeline._validate_inspected_scene` | actual-plane mapping rejection and Phase 2 readiness tests | Covered |
| REQ-EXEC-004 | `run_scene_pipeline` confinement is implemented; canonical per-render placement is pending under `GAP-STORAGE-001` | Existing workdir-confinement test; canonical-layout coverage not yet implemented | Partial |
| REQ-EXEC-005, REQ-EXEC-006, REQ-CARD-005, REQ-CARD-009, REQ-CARD-012 | `scene_pipeline.py`; atomic `save_scene` | successful history, failed inspection, interrupted-save/history tests | Covered |
| REQ-EXEC-007, REQ-CLI-001 through REQ-CLI-004 | `cli.py`; `ui.py` | `test_cli.py`; `test_scene_pipeline.py`; `test_app_config.py`; `test_ui.py` | Covered |
| REQ-PSF-004, REQ-PSF-006, REQ-ARCH-001 | `pipeline._load_or_build_reprojected` | existing dual-branch pipeline/PSF tests plus processing regression suite | Covered |
| REQ-RENDER-002, REQ-RENDER-003, REQ-RENDER-008 | `pipeline.py`; `scene_pipeline.py`; `render_jobs.py`; `ui.py` | cancellation and background-job cases in `test_scene_pipeline.py` | Covered |
| REQ-NAV-003, REQ-NAV-004, REQ-NAV-006, REQ-RENDER-006 through REQ-RENDER-008 | `scene_workflow.merge_render_completion`; `render_jobs.request_cancellation_before_departure`; `ui.py` | Phase 6 merge, persistence, identity, and departure cases in `test_ui.py` and `test_scene_pipeline.py` | Covered |
| REQ-NAV-003, REQ-NAV-006, REQ-RENDER-006 through REQ-RENDER-008, REQ-CARD-005, REQ-CARD-009, REQ-CARD-012 | `scene_card.save_scene` optimistic previous-document check; `scene_pipeline.run_scene_pipeline` latest-card merge | Phase 7 concurrent metadata, concurrent input, and intervening-save regressions in `test_scene_cards.py` and `test_scene_pipeline.py` | Covered |
| REQ-CARD-013 through REQ-CARD-016 | Planned canonical path builders and artifact producer/consumer migration under `GAP-STORAGE-001` | Layout, containment, identity, cache separation, immutability, and external-export tests are not yet implemented | Gap |
| REQ-MIG-006 | JSON pipeline/UI/CLI plus Phase 5 retirement | dependency/import/document checks and full suite | Covered |

## Verification

Focused Phase 3 execution tests: 9 passed. Processing regression selection, including the per-plane PSF branch case: 33 passed. The repository-wide result is recorded in `phase3_scene_execution.md`.

The canonical processing path imports `processing_config.py`. The normal CLI and UI
accept scene-card JSON and reject YAML. The former YAML loader, temporary translator,
legacy examples, dependency, and compatibility tests were removed in Phase 5.

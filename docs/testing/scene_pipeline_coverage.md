# Phase 3 Scene-Card Execution Coverage

## Scope

This matrix covers the JSON scene-card execution seam, exact product pinning, inspected-plane validation, native-frame PSF ordering, CLI cutover, render-history commit, and safe-boundary cancellation.

| Requirement | Implementation | Tests | Status |
| --- | --- | --- | --- |
| REQ-EXEC-001 | `scene_execution.py`; `pipeline.py` pinned selection path | `test_scene_pipeline_uses_local_pin_records_history_and_writes_no_yaml` | Covered |
| REQ-EXEC-002, REQ-IFACE-004, REQ-IFACE-005 | `prepare_scene_execution`; `_local_product_manifest` | local-pin, missing-pin, exact-candidate assertions | Covered |
| REQ-EXEC-003, REQ-PROJ-015 through REQ-PROJ-018 | `scene_readiness.py`; `pipeline._validate_inspected_scene` | actual-plane mapping rejection and Phase 2 readiness tests | Covered |
| REQ-EXEC-004, REQ-CARD-018, REQ-CARD-019 | `run_scene_pipeline` confinement, render-private scratch, and canonical branch outputs from `artifact_paths.py` | workdir confinement, exact render-private cache placement, and actual canonical scene-render placement assertions | Covered |
| REQ-EXEC-005, REQ-EXEC-006, REQ-CARD-005, REQ-CARD-009, REQ-CARD-012 | `scene_pipeline.py`; atomic `save_scene` | successful history, failed inspection, interrupted-save/history tests | Covered |
| REQ-EXEC-007, REQ-CLI-001 through REQ-CLI-004 | `cli.py`; `ui.py` | `test_cli.py`; `test_scene_pipeline.py`; `test_app_config.py`; `test_ui.py` | Covered |
| REQ-PSF-004, REQ-PSF-006, REQ-ARCH-001 | `pipeline._load_or_build_reprojected` | existing dual-branch pipeline/PSF tests plus processing regression suite | Covered |
| REQ-RENDER-002, REQ-RENDER-003, REQ-RENDER-008 | `pipeline.py`; `scene_pipeline.py`; `render_jobs.py`; `ui.py` | cancellation and background-job cases in `test_scene_pipeline.py` | Covered |
| REQ-NAV-003, REQ-NAV-004, REQ-NAV-006, REQ-RENDER-006 through REQ-RENDER-008 | `scene_workflow.merge_render_completion`; `render_jobs.request_cancellation_before_departure`; `ui.py` | Phase 6 merge, persistence, identity, and departure cases in `test_ui.py` and `test_scene_pipeline.py` | Covered |
| REQ-NAV-003, REQ-NAV-006, REQ-RENDER-006 through REQ-RENDER-008, REQ-CARD-005, REQ-CARD-009, REQ-CARD-012 | `scene_card.save_scene` optimistic previous-document check; `scene_pipeline.run_scene_pipeline` latest-card merge | Phase 7 concurrent metadata, concurrent input, and intervening-save regressions in `test_scene_cards.py` and `test_scene_pipeline.py` | Covered |
| REQ-CARD-013 through REQ-CARD-019 | centralized branch path builder, content identities, immutable render directories, transient scratch boundary, and explicit legacy resolver | canonical/legacy path tests, scene registration, scratch placement, history immutability and external/optional-managed export tests | Covered |
| REQ-MIG-006 | JSON pipeline/UI/CLI plus Phase 5 retirement | dependency/import/document checks and full suite | Covered |
| REQ-SELECT-006 through REQ-SELECT-008 | `mast._enrich_products`; parent-observation grouping; Level-3 product-role preference; known-depth ranking | parent metadata, association mosaic preference, and unknown-depth tests in `test_mast.py` | Covered |
| REQ-WCS-008 | `pipeline._validate_selected_plane_coverage` | zero and nonzero footprint cases in `test_pipeline_modes.py` | Covered |
| REQ-CARD-017 | `scene_card._verify_file`; streamed dependency and save validation | `test_dependency_verification_streams_local_asset` in `test_scene_cards.py` | Covered |
| REQ-FITS-001 through REQ-FITS-004 | `fitsio._load_validity_mask`; `reprojection.reproject_plane`; aligned-plane metadata | combined DQ/WHT/CTX, native-unit, masked-reprojection, and footprint round-trip tests | Covered |
| REQ-NORM-001 through REQ-NORM-006 | scene/processing normalization models; `mapping.compose_channels_with_diagnostics`; pipeline provenance | scale-matching, valid-pixel percentile, mixed-unit warning, contribution, schema, and pipeline provenance tests | Covered |
| REQ-NORM-008 | `mapping.compose_channels_with_diagnostics`; `tone.apply_tone`; pipeline tone handoff | `test_output_tone_percentiles_exclude_uncovered_pixels`; channel-coverage assertions in `test_percentile_normalization_excludes_pixels_outside_footprint` | Covered |
| REQ-INV-001 through REQ-INV-004 | `scene_workflow.inspect_scene_artifacts`; `ui._render_artifacts` | local FITS unit/mask inventory and mixed-unit warning tests in `test_ui.py` | Covered |
| REQ-PROJ-004, REQ-PROJ-006, REQ-PROJ-007, REQ-FIND-002 | `scene_execution.prepare_scene_execution`; `scene_workflow.draft_from_resolver_match` | resolved-name render bridge and repeated-query resolver regressions in `test_scene_pipeline.py` and `test_ui.py` | Covered |

## Verification

Focused Phase 3 execution tests: 9 passed. Processing regression selection, including the per-plane PSF branch case: 33 passed. The repository-wide result is recorded in `phase3_scene_execution.md`.

The canonical processing path imports `processing_config.py`. The normal CLI and UI
accept scene-card JSON and reject YAML. The former YAML loader, temporary translator,
legacy examples, dependency, and compatibility tests were removed in Phase 5.

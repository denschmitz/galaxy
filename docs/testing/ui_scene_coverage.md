# UI and Scene Card Acceptance Coverage

Date: 2026-09-10. Scope: requirements and specifications from the five-screen/scene-card pass.
Source: [Design requirements](../design_requirements.md).
Specifications: [User flows](../user_flows.md) and [Scene card schema](../scene_card_schema.md).

Phase 5 completes the deterministic workflow scenarios identified below. External
interfaces are exercised through offline fixtures; the opt-in public archive test is
not required for compliance.

## Traceability matrix

Ranges include every requirement identifier between their endpoints.

| Requirement(s) | Related implementation | Existing related tests | Planned acceptance evidence | Status |
| --- | --- | --- | --- | --- |
| REQ-NAV-001 through REQ-NAV-007 | ui.py; scene_workflow.py; render_jobs.py | test_ui.py; test_app_config.py; test_scene_pipeline.py | AC-NAV | Covered, including cancellation-before-departure and preservation of post-launch edits |
| REQ-FIND-001 through REQ-FIND-008 | src/galaxy/ui.py; src/galaxy/targeting.py; src/galaxy/discovery_sources.py | tests/test_ui.py; tests/test_discovery_sources.py; tests/test_targeting.py | AC-FIND | Covered |
| REQ-REFINE-001 through REQ-REFINE-018 | src/galaxy/ui.py; scene_workflow.py; mast.py; mapping.py | tests/test_ui.py; tests/test_mast.py; tests/test_mapping_tone.py; pipeline footprint tests | AC-REFINE | Covered |
| REQ-RENDER-001 through REQ-RENDER-009 | ui.py; render_jobs.py; scene_workflow.py; scene_pipeline.py; pipeline.py | test_ui.py; test_scene_pipeline.py; test_pipeline_modes.py | AC-RENDER | Covered, including stale completion merge and identity isolation |
| REQ-SAVE-001 through REQ-SAVE-009 | src/galaxy/ui.py; scene_workflow.py; scene_pipeline.py | tests/test_ui.py; test_scene_pipeline.py; test_planes_and_exports.py | AC-SAVE | Covered for independent save/export, aspect-preserving resize, overwrite guard, thumbnails, and encoded PNG/TIFF |
| REQ-LIB-001 through REQ-LIB-006 | src/galaxy/scene_workflow.py; src/galaxy/ui.py | tests/test_ui.py | AC-LIB | Covered, including unsaved duplication |
| REQ-LIB-007 through REQ-LIB-011 | `list_project_library`; `LibraryOrigin`; `_render_library`; `_save_active`; `save_example_as_user_scene` | `test_project_library_separates_example_and_user_scenes`; `test_example_save_creates_new_identity_without_modifying_source`; `test_streamlit_normal_launch_opens_pillars_example_and_inventory` | AC-HUMAN-001 | Covered; manual signoff pending |
| REQ-ART-001 through REQ-ART-005 | `inspect_scene_artifacts`; `_render_artifacts` | `test_pillars_inventory_is_remote_only_and_ignores_unreferenced_files`; `test_inventory_distinguishes_missing_and_corrupt_sources`; `test_inventory_distinguishes_current_and_stale_render`; Streamlit first-flow test | AC-HUMAN-001 | Covered; manual signoff pending |
| REQ-IFACE-001 through REQ-IFACE-005 | targeting.py; mast.py; ui.py | test_targeting.py; test_mast.py; test_scene_pipeline.py | AC-INTERFACE | Covered: explicit resolver and archive outcomes plus exact unavailable-product identity |
| REQ-SOURCE-001 through REQ-SOURCE-004; REQ-CACHE-001 through REQ-CACHE-004 | discovery_sources.py; discovery_cache.py; cache.py; ui.py | test_discovery_sources.py; test_discovery_cache.py; test_ui.py | AC-SOURCE | Covered |
| REQ-CARD-001 through REQ-CARD-012 | src/galaxy/scene_models.py; scene_card.py; scene_readiness.py; ui.py | tests/test_scene_cards.py; tests/test_ui.py | AC-CARD | Covered |
| REQ-PROJ-001 through REQ-PROJ-026 | scene-card modules; processing_config.py; ui.py | tests/test_scene_cards.py; test_scene_pipeline.py; test_ui.py | AC-CARD; AC-SETTINGS | Covered |
| REQ-UI-005; REQ-CLI-002 | src/galaxy/ui.py; scene_workflow.py; cli.py; scene_pipeline.py | tests/test_ui.py; tests/test_cli.py; test_scene_pipeline.py | AC-ENTRY | Covered |
| REQ-UI-006 | Stable keyed radio and checkbox widgets in `src/galaxy/ui.py` | `test_streamlit_controls_commit_after_one_activation`; browser single-click verification | AC-HUMAN-001 | Automated coverage complete; Edge human retest pending |
| REQ-EXEC-001 through REQ-EXEC-007 | scene_execution.py; scene_pipeline.py; pipeline.py; cli.py | tests/test_scene_pipeline.py; tests/test_cli.py | AC-PIPELINE; AC-ENTRY | Covered outside UI |
| REQ-DISC-006 | discovery_sources.py; scene_workflow.py; ui.py | tests/test_discovery_sources.py | AC-FIND; AC-CARD | Covered |
| REQ-ARCH-001; REQ-ARCH-002; REQ-PSF-004 | src/galaxy/pipeline.py; src/galaxy/ui.py | tests/test_pipeline_modes.py; tests/test_psf.py; tests/test_ui.py | AC-PIPELINE | Covered |
| REQ-MAN-003; REQ-WCS-001; REQ-MAP-001; REQ-TONE-001; REQ-LOG-004; REQ-LOG-005 | selection.py; reprojection.py; mapping.py; tone.py; logging_utils.py; scene_execution.py | processing and scene-card suites | AC-SETTINGS | Covered |

Unchanged processing requirements retain their existing test obligations. This matrix is not a claim of full repository-wide coverage. Existing source-hint model coverage remains in [Discovery source coverage](discovery_source_coverage.md).

## Acceptance scenario outlines

### Configuration coverage addition

| Requirement(s) | Related implementation | Existing related tests | Planned acceptance evidence | Status |
| --- | --- | --- | --- | --- |
| REQ-CONFIG-001 through REQ-CONFIG-010; REQ-CLI-004 | src/galaxy/app_config.py; cli.py; ui.py; scene_workflow.py | tests/test_app_config.py; tests/test_cli.py; tests/test_ui.py | AC-CONFIG | Covered |

### AC-CONFIG

Start from an isolated checkout root without a config file and verify creation of a JSON object containing `scene_directory = artifacts/scenes`. Repeat from a different working directory and verify the same root-relative default. Repeat with `--scene-dir` and verify that the default config is still created while the override wins for the invocation. Exercise a custom configured directory, a missing key, absolute paths, relative config paths, and relative command-line paths. Confirm existing config bytes remain unchanged and Saved scenes/new-save defaults use the effective directory. Invalid JSON, a non-object config, blank/non-string path values, read failures, and creation failures must report diagnostics without silently falling back. No acceptance test is claimed executed in this documentation pass.

### AC-NAV

Launch without input and observe Discovery; navigate all five screens; preserve active edits; save a draft from Refinement and Render. On replacing/closing edited work, exercise Save, Discard, Cancel, and a failing Save. Verify operation states and recovery preserve the prior scene.

### AC-FIND

Use fixtures for common names, aliases, ambiguous names, unknown names, coordinate pairs, and tracker cards. Verify chosen identity, field errors, independent tracker failure, selectable missing-image placeholders, draft creation, and restored gallery query/filters/scroll.

### AC-REFINE

Use two authoritative observation IDs sharing one name, each with multiple products and versions. Verify separate grouping, available/unknown metadata, individual selection, and filter enablement. Compare recommendation outputs against the configured selection policy; require explicit Apply and explain missing metadata. Edit mappings and remove a referenced plane. Verify the render gate detects that change. Check existing canvas retention, default circle/box enclosure, numerical crop edits, footprint display, missing region input, and draft saving.

### AC-RENDER

Render a fixed input snapshot, change live settings, and verify the completed image is linked only to its snapshot. Exercise progress, cancellation at a stage boundary, failure retention, mapping/tone edits, out-of-date previews, branch selection, and return to Refinement.

### AC-SAVE

Save independently of export. Export PNG and TIFF with valid dimensions, then change resolution and require a matching rerender without changing the sky frame. Test incompatible aspect ratio and existing-file confirmation. Verify current generated versus attributed discovery thumbnail/placeholder behavior, retained render history, and independent save/export failure reporting.

### AC-LIB

Test empty library, valid cards, one corrupt card among valid cards, missing thumbnail, missing cached source, and unavailable pinned archive product. Open restores settings; Duplicate produces a new identifier and independent edits. Metadata displays derived readiness and actual saved time.

### AC-INTERFACE

Fake resolver outcomes for resolved/ambiguous/unresolved/failed; fake MAST responses for zero results, failure, incomplete retrieval, and unavailable selected product. Verify exact download identities and no silent substitutions. No live network is required for these tests.

### AC-SOURCE

A resolved target with zero archive candidates must not show usable coverage. Verify thumbnail source/credit retention and distinct labels for external thumbnails versus generated previews. Exercise fresh and stale cached results, explicit stale reuse, and forced refresh.

### AC-CARD

Validate minimal metadata-only JSON, progressive partial sections, full render inputs, both thumbnail kinds, and appended renders/exports. Reject invalid types, missing metadata, unknown fields/versions, duplicates, broken references, unsafe local paths, and invalid numeric bounds. Verify semantic save/reopen equality, exact selected IDs, optional binary folder behavior, derived readiness, immutable historical input snapshots, and interrupted-save recovery. Reopen must not execute export destinations.

### AC-SETTINGS

Round-trip every declared scene setting through the JSON model, including search/pinned selection precedence, view state versus actual framing, plane enablement, mapping overrides, channel tone, PSF asset references, and runtime policy. Feed the restored settings into discovery/composition and confirm consistent candidates, output geometry, and provenance. Check diagnostics name scene cards and identify field paths.

### AC-ENTRY

Open scene card JSON, candidate manifest JSON, aligned planes, and workdir inputs. Verify document-type discrimination and screen routing. With no explicit input, workspace artifacts appear as choices without bypassing Discovery. Verify CLI execution accepts a render-ready scene card.

### AC-PIPELINE

After the ordering contract is reconciled, verify native-frame PSF processing precedes reprojection for the processed branch, source preservation holds, and both original and processed branches remain traceable. This pass does not change pipeline code.

### AC-HUMAN-001

From a normal offline launch with an empty configured user scene directory, open the
project selector and verify that Pillars of Creation appears exactly once under
Examples. Open it into Scene refinement and verify its protected-example marker,
six exact selected MAST products, six expected filters, and artifact inventory of
six remote-only sources with no local sources, aligned planes, renders, exports, or
missing/corrupt references. Edit the title and tone, save as a new scene, reopen the
copy from Saved scenes, and verify that the bundled Pillars JSON bytes are unchanged.

## Documentation checks for this pass

Check unique requirement definitions, retention of historical IDs, existence of
referenced documents and source/test paths, complete UF-01 through UF-05 coverage,
and parsable JSON examples. Automated application coverage is recorded above; the
human interaction and visual signoff in AC-HUMAN-001 remains a separate acceptance
event.

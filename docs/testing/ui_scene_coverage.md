# UI and Scene Card Acceptance Coverage

Date: 2026-09-22. Scope: requirements and specifications from the five-screen/scene-card pass.
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
| REQ-REFINE-001 through REQ-REFINE-011; REQ-REFINE-013 through REQ-REFINE-018 | src/galaxy/ui.py; scene_workflow.py; mast.py; mapping.py | tests/test_ui.py; tests/test_mast.py; tests/test_mapping_tone.py; pipeline footprint tests | AC-REFINE | Covered |
| REQ-DATA-010 through REQ-DATA-011; REQ-MAN-004 through REQ-MAN-006; REQ-REFINE-019 through REQ-REFINE-032; REQ-SELECT-009 through REQ-SELECT-015 | `selection.py`; `mast.py`; `selection_guidance.py`; `scene_workflow.py`; `scene_models.py`; `ui.py` | `tests/test_selection_guidance.py`; `tests/test_mast.py`; `tests/test_ui.py`; `tests/test_scene_cards.py`; `tests/test_discovery_cache.py` | AC-SELECT-GUIDANCE | Covered; GAP-GUIDANCE-001 closed 2026-09-22 |
| REQ-REFINE-012; REQ-REFINE-033 through REQ-REFINE-041; REQ-WCS-009 through REQ-WCS-016 | `viewport_framing.py`; `pipeline.py`; `scene_pipeline.py`; `scene_workflow.py`; `ui.py` | `tests/test_viewport_framing.py`; automatic first-render persistence in `tests/test_scene_pipeline.py`; geometric preview/apply, selection-reconciliation, and stale-overlay flows in `tests/test_ui.py`; measured three-file Horsehead visual check | AC-FRAME-FIT | Covered; GAP-FRAME-001, GAP-FRAME-002, and GAP-APPLY-001 closed |
| REQ-RENDER-001 through REQ-RENDER-009 | ui.py; render_jobs.py; scene_workflow.py; scene_pipeline.py; pipeline.py | test_ui.py; test_scene_pipeline.py; test_pipeline_modes.py | AC-RENDER | Covered, including current-live-state persistence at launch, stale completion merge, and identity isolation |
| REQ-SAVE-001 through REQ-SAVE-009 | src/galaxy/ui.py; scene_workflow.py; scene_pipeline.py | tests/test_ui.py; test_scene_pipeline.py; test_planes_and_exports.py | AC-SAVE | Covered for independent save/export, aspect-preserving resize, overwrite guard, thumbnails, and encoded PNG/TIFF |
| REQ-LIB-001 through REQ-LIB-006 | src/galaxy/scene_workflow.py; src/galaxy/ui.py | tests/test_ui.py | AC-LIB | Covered, including unsaved duplication |
| REQ-LIB-007 through REQ-LIB-019 | `list_project_library`; `example_user_path`; `materialize_example`; `open_example_user_copy`; `_render_library_entries`; `_render_example_overwrite_confirmation` | Example materialization, overwrite, asset retention, thumbnail, catalog-content, and Streamlit flow tests in `tests/test_ui.py` and `tests/test_scene_cards.py` | AC-HUMAN-001 | Automated coverage complete; manual Edge signoff pending |
| REQ-LIB-020 through REQ-LIB-026 | `associated_asset_root`; `delete_library_scene`; `_render_project_delete_confirmation`; `_render_library_entries` | `tests/test_project_deletion.py`; deletion interaction in `tests/test_ui.py` | AC-LIB | Covered; GAP-DELETE-001 closed 2026-09-24 |
| REQ-LIB-027 through REQ-LIB-034 | Planned: scene_workflow.py; ui.py; scene-card persistence | Required clone storage-name and inline rename regressions not implemented | AC-LIB inline title/clone scenarios below | Not implemented; GAP-TITLE-001 open |
| REQ-ART-001 through REQ-ART-005 | `inspect_scene_artifacts`; `_render_artifacts` | `test_pillars_inventory_is_remote_only_and_ignores_unreferenced_files`; `test_inventory_distinguishes_missing_and_corrupt_sources`; `test_inventory_distinguishes_current_and_stale_render`; Streamlit first-flow test | AC-HUMAN-001 | Covered; manual signoff pending |
| REQ-IFACE-001 through REQ-IFACE-005 | targeting.py; mast.py; ui.py | test_targeting.py; test_mast.py; test_scene_pipeline.py | AC-INTERFACE | Covered: explicit resolver and archive outcomes plus exact unavailable-product identity |
| REQ-SOURCE-001 through REQ-SOURCE-004; REQ-CACHE-001 through REQ-CACHE-005 | discovery_sources.py; discovery_cache.py; cache.py; ui.py | test_discovery_sources.py; test_discovery_cache.py; test_ui.py | AC-SOURCE | Covered, including canonical application-cache placement |
| REQ-CARD-001 through REQ-CARD-012 | src/galaxy/scene_models.py; scene_card.py; scene_readiness.py; ui.py | tests/test_scene_cards.py; tests/test_ui.py | AC-CARD | Covered |
| REQ-PROJ-001 through REQ-PROJ-026 | scene-card modules; processing_config.py; ui.py | tests/test_scene_cards.py; test_scene_pipeline.py; test_ui.py | AC-CARD; AC-SETTINGS | Covered |
| REQ-UI-005; REQ-CLI-002 | src/galaxy/ui.py; scene_workflow.py; cli.py; scene_pipeline.py | tests/test_ui.py; tests/test_cli.py; test_scene_pipeline.py | AC-ENTRY | Covered |
| REQ-UI-006 | Stable keyed radio and checkbox widgets in `src/galaxy/ui.py` | `test_streamlit_controls_commit_after_one_activation`; browser single-click verification | AC-HUMAN-001 | Automated coverage and isolated Chromium single-click verification complete 2026-10-03; Edge user signoff pending |
| REQ-COV-008, REQ-NORM-014 | Independent output-footprint and brightness-reference controls plus locked normalization proposal/preview/Apply in `src/galaxy/ui.py` | numerical-core, accepted-default, mapping-application, persistence and full-suite regression tests | AC-HUMAN-001 | Accepted policy and integrated browser control/reopen check complete 2026-10-03 |
| REQ-TONE-002 through REQ-TONE-013 | Tone application/method/gamut controls, method-specific parameters, explicit single-main-stretch action, and auto proposal Preview/Recompute/Apply in `src/galaxy/ui.py` | shared-intensity/GHS/auto numerical tests; Streamlit control/preset test; Apply/save/reopen/no-drift test; real-scene A/B generation | AC-HUMAN-001 | Automated, retained-real-scene, and integrated browser control/reopen checks complete 2026-10-03; final user presentation acceptance remains explicit |
| REQ-EXEC-001 through REQ-EXEC-007 | scene_execution.py; scene_pipeline.py; pipeline.py; cli.py | tests/test_scene_pipeline.py; tests/test_cli.py | AC-PIPELINE; AC-ENTRY | Covered outside UI |
| REQ-DISC-006 | discovery_sources.py; scene_workflow.py; ui.py | tests/test_discovery_sources.py | AC-FIND; AC-CARD | Covered |
| REQ-ARCH-001; REQ-ARCH-002; REQ-PSF-004 | src/galaxy/pipeline.py; src/galaxy/ui.py | tests/test_pipeline_modes.py; tests/test_psf.py; tests/test_ui.py | AC-PIPELINE | Covered |
| REQ-WCS-005 through REQ-WCS-007 | `edit_scene`; `matching_render`; `_reject_registered_output_overlap`; reusable explicit scene workdir | `test_canvas_change_can_replace_unreferenced_reprojections`; `test_scene_workdir_cannot_overwrite_registered_render_assets` | AC-PIPELINE; AC-CARD | Covered |
| REQ-INV-001 through REQ-INV-004, REQ-NORM-006 | source inventory FITS metadata inspection, normalization display fields, and adjacent warning in `ui._render_artifacts` | `test_inventory_reports_units_masks_normalization_and_mixed_unit_warning`; Pillars inventory inspection | AC-UI; AC-CARD | Covered |
| REQ-NORM-007 | `scene_workflow.materialize_render_defaults` persists the robust valid-pixel percentile policy for newly materialized mappings | `test_defaults_are_explicit_and_wavelength_ordered` | AC-UI; AC-CARD | Covered |
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

Use two authoritative observation IDs sharing one name, each with multiple products and versions. Verify separate grouping, available/unknown metadata, individual selection, and filter enablement. Compare recommendation outputs against the configured selection policy; require explicit Apply and explain missing metadata. Applying a reduced selection to an asset-backed duplicate shall preserve matching local source references, replace stale mapping/processing defaults with settings for exactly the selected filters, retain the accepted canvas, and enable Render when no independent issue remains. Edit mappings and remove a referenced plane. Verify the render gate detects that change. Check existing canvas retention, default circle/box enclosure, numerical crop edits, footprint display, missing region input, and draft saving.

### AC-FRAME-FIT

Use deterministic FITS fixtures whose celestial WCS footprints overlap, form a
mosaic, cross right ascension zero, use different pixel scales and rotations, are
disconnected but nearby, and are widely separated. Verify that the proposed canvas
contains every selected valid footprint after padding, uses the deterministic
minimum-area orientation, rounds raster dimensions upward, and coarsens scale to
the initial-preview limit without oversampling the finest input. Verify automatic
application only for a new scene's first warning-free fit, explicit application on
later fits, preservation of an accepted or edited frame after selection changes,
and identification of newly selected footprints outside it. Exercise each warning
threshold and verify component count, span, frame size, fill fraction, pixel size,
and memory diagnostics. Missing celestial WCS and infeasible TAN unions must fail
fitting with product-specific guidance. Reopen the saved scene and verify its
materialized canvas is unchanged without rereading source FITS files.

### AC-SELECT-GUIDANCE

Use a deterministic manifest containing duplicate archive rows, conflicting exposure
metadata, HST and JWST candidates, multiple instruments, repeated filters, known and
unknown file sizes, and product alternatives. Verify that duplicate downloadable
identities collapse to one candidate, conflicting fields are labeled, and summary
counts and byte totals use unique identities. Exercise `Preview set (up to 3
products)`, `Full filter set (one per instrument/filter)`, and `Custom selection` under all,
HST-only, and JWST-only scopes. Verify deterministic restoration, explicit Apply,
clear/restore controls, grouped alternatives, and the concise explanation grammar.
Save before Apply and verify the scene references the candidate manifest and reopens
without a new query. Confirm the primary readiness area shows workflow actions while
raw field paths appear only under `Technical readiness details`.

Verification completed 2026-09-22: `tests/test_selection_guidance.py` covers
normalization conflicts, all required modes and scopes, deterministic custom state,
unique size totals, concise explanations, alternatives, pre-Apply persistence,
missing/corrupt asset reporting, restoration, and stage guidance. The complete
offline suite reported 238 passed and one opt-in live-archive test skipped.

### AC-RENDER

Render a fixed input snapshot, change live settings, and verify the completed image is linked only to its snapshot. Starting a preview from an existing saved draft with newer live selections or defaults must persist those current settings before the file-backed worker starts. Exercise progress, cancellation at a stage boundary, failure retention, mapping/tone edits, out-of-date previews, branch selection, and return to Refinement.

### AC-SAVE

Save independently of export. Export PNG and TIFF with valid dimensions, then change resolution and require a matching rerender without changing the sky frame. Test incompatible aspect ratio and existing-file confirmation. Verify current generated versus attributed discovery thumbnail/placeholder behavior, retained render history, and independent save/export failure reporting.

### AC-LIB

Test empty library, valid cards, one corrupt card among valid cards, missing thumbnail, missing cached source, and unavailable pinned archive product. A user-scene Duplicate produces a committed new identifier, display title `<source-title> copy`, and canonical filename/asset root derived from `<source-title>` plus the new ID without the generated `copy` label. It removes render/export history and materializes verified retained inputs under the new asset root using a same-volume hard link or bounded-memory copy fallback. Verify the duplicate remains usable after either scene path is unlinked and that a missing source publishes no card. For a user scene, activate its title by pointer and keyboard, verify an in-place prefilled input, commit by the supported explicit action, cancel without mutation, reject invalid input without mutation, and verify atomic save failure/concurrent change handling. A successful title edit updates title/timestamp and any active view while preserving identity, revision, JSON/asset paths, history, dependencies, and render currency. Verify no edit affordance on bundled-example source entries and disable rename during associated write operations. An example Duplicate preserves the example identity and exact filename in the user scene directory, requires confirmation before JSON replacement, and retains the paired asset folder. Example Open resolves through that user copy. Metadata displays derived readiness and actual saved time. For project deletion, verify that bundled examples have no Delete action; a user scene requires confirmation naming its exact card and asset root; cancellation changes nothing; success moves both members to recovery, closes an active scene, and refreshes the library; application cache, external exports, and unrelated scenes remain byte-for-byte unchanged. Inject a failure after moving each member and verify rollback, failure reporting, retained active state, and filesystem-derived refresh. Verify deletion is unavailable during associated save, acquisition, render, and export operations.

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
project selector and verify that `examples/Pillars.json` appears exactly once under
Examples with a placeholder. Open it and verify that the application first creates
and then opens the exact-name user copy in the effective scene directory while the
bundled JSON remains unchanged. Create a valid user-copy thumbnail and verify the
example entry uses it. Exercise Duplicate both without a collision and with an
existing user copy: cancellation changes nothing; confirmation replaces only the
JSON and preserves the paired binary asset folder byte-for-byte. Change the canvas
and verify that unreferenced stale reprojections may be replaced while sources and
artifacts referenced by retained successful render records are not overwritten.

## Documentation checks for this pass

Check unique requirement definitions, retention of historical IDs, existence of
referenced documents and source/test paths, complete UF-01 through UF-05 coverage,
and parsable JSON examples. Automated application coverage is recorded above; the
human interaction and visual signoff in AC-HUMAN-001 remains a separate acceptance
event.


## Bridge UI integration (2026-10-08)

| Requirements | Implementation | Tests/evidence | Status |
|---|---|---|---|
| REQ-BRIDGE-004,016..020 | `ui._render_bridge`, scene models/schema, execution/workflow/readiness, pipeline checkpoints | `tests/test_bridge_integration.py`: saved default/Off/duplicate, actual-job preview, running switch lock, stale snapshot/reuse, completion redraw; isolated in-app Chromium Off save/reopen, On preview and TIFF export, toggle-Off stale export rejection | Implementation, automated and technical browser complete; user full-scene/Edge acceptance pending |

Evidence and commands: [bridge plan](../compliance_status/reprojection_bridge_plan.md).
The browser QA scene is isolated under artifacts; existing user scenes were not
changed. Preview PNG supports visual acceptance; TIFF export is optional.

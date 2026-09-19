# Phase 4 UI Workflow Compliance Plan

Date: 2026-09-14.
Status: complete with retained gaps documented below.

## Baseline

Phase 3 established JSON scene-card execution, but the Streamlit entrypoint still opens
legacy YAML projects and does not use the configured scene directory as a scene library.
The durable gap register identifies GAP-CONFIG-001, GAP-SCENE-001, GAP-UI-001, and
GAP-DISC-001 as the applicable starting gaps.

## Phases

1. **4A - workflow domain layer:** add deterministic input routing, scene-library
   inspection, target/hint draft creation, canvas/default materialization,
   recommendation application, render currency checks, duplication, and export
   planning as UI-independent functions.
2. **4B - five-screen shell:** make Discovery the normal opening screen and implement
   Discovery, Scene refinement, Render and adjust, Output and save, and Saved scenes
   over one session-owned scene-card draft.
3. **4C - persistence and execution:** route draft saves and the library through the
   effective `scene_directory`; run the canonical scene-card pipeline; preserve exact
   selected product identities, progress, result identity, and independent save/export
   outcomes.
4. **4D - verification and closeout:** add offline unit and Streamlit-boundary tests,
   update the acceptance matrix and known-gap register, remove remaining normal UI YAML
   behavior, and run the full test suite. Any intermediary findings are either closed
   here or retained explicitly in `known_gaps.md`.

Pixel-exact layout, local fuzzy name catalogs, and other items listed as deferred in
the requirements are outside this phase.

## Result

- Added scene_workflow.py as the UI-independent contract boundary for artifact
  routing, library inspection, exact product pins, derived readiness, default frame
  and composition materialization, duplication, render currency, and guarded export.
- Replaced the YAML-oriented Streamlit entrypoint with Discovery, Scene refinement,
  Render and adjust, Output and save, and Saved scenes. Normal startup opens
  Discovery; explicit scene/manifest/FITS inputs follow the specified routes.
- Connected new saves and Saved scenes to the effective application scene_directory,
  including the command-line override.
- Added Save/Discard/Cancel handling before scene replacement, independent
  save/export outcomes, missing dependency reporting, current/stale render identity,
  generated render thumbnails, and actual PNG/TIFF encoding.
- Removed the internal pipeline's legacy YAML sidecar output. The isolated translator,
  YAML examples, loader, and dependency were not deleted in this phase; see
  GAP-SCENE-001.
- Verification: 194 passed, 1 opt-in live archive test skipped.

## Retained gaps

The external latest-release adapter/gallery, explicit ambiguous-name resolver outcome,
and a cancellable background render worker remain open under GAP-DISC-001 and
GAP-UI-001. These are not represented as passing acceptance scenarios.

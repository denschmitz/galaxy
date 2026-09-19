# Known Gaps

This file tracks open compliance and implementation gaps identified during review and design passes.

## 2026-06-08 Multi-Method Discovery Phase 0 Baseline

Status: closed 2026-09-14. All gaps recorded in this baseline have dispositions below.

### GAP-DOC-001 Source Of Truth Filename Mismatch

Status: closed 2026-09-10. The normative source of truth is now `docs/design_requirements.md`; `docs/design-requirements.md` is a compatibility link.

Impact: future agents may look for the wrong requirements file before implementation or review work.

Resolution: canonical filename now matches repository instructions without maintaining duplicate requirements.

### GAP-COMP-001 Missing Compliance Status Directory

Status: closed 2026-09-10. No compliance directory existed at the original baseline; the directory and durable gap register now exist.

Impact: prior review findings and deferred compliance items may not be discoverable.

Resolution: maintain this file as the durable gap register for future passes.

### GAP-DISC-001 Multi-Method Discovery Not Yet Implemented

Status: closed 2026-09-14.

The Yuval Harpaz CSV adapter, source attribution, offline filtering fixtures,
missing-thumbnail selection, isolated source failure behavior, and hint-to-scene/UI
conversion are implemented. MAST remains the authoritative product-discovery path.

## 2026-09-10 Scene Card and Screen Specification

### GAP-CONFIG-001 Application Storage Configuration Pending

Status: closed 2026-09-14.

Application configuration loading, initialization, and CLI/UI startup integration are
implemented. Phase 4 routes Saved scenes and default new-scene saves through the
effective scene directory.

Resolution evidence: src/galaxy/app_config.py, src/galaxy/scene_workflow.py,
src/galaxy/ui.py, tests/test_app_config.py, and tests/test_ui.py.

### GAP-SCENE-001 Canonical JSON Scene Card UI Integration Remaining

Status: closed 2026-09-14.

The strict JSON model, persistence, canonical pipeline, CLI, and five-screen UI use
scene cards. The normal UI/CLI reject legacy YAML and the pipeline no longer writes a
YAML sidecar.

Phase 5 removed the isolated translator, legacy loader, translated YAML originals,
PyYAML dependency, and legacy compatibility tests under REQ-MIG-006.

### GAP-UI-001 Five-Screen Workflow Not Verified

Status: closed 2026-09-14.

Discovery, Refinement, Render, Output/save, and Saved scenes are implemented over the
scene-card workflow layer. Offline tests cover JSON/FITS routing, target drafts,
selection pins, recommendations, frames, stale results, library isolation,
duplication, thumbnail creation, and guarded PNG/TIFF export.

Phase 5 added the external tracker gallery, explicit resolver outcomes and ambiguous
selection, a background render job with safe-boundary cancellation, operation-state
reporting, guarded active-scene close, and unsaved independent duplication.

### GAP-ARCH-001 Existing PSF Stage Ordering Conflict

Status: closed 2026-09-14.

REQ-ARCH-001 now places optional native-frame PSF processing on a separate derived branch before independent reprojection, followed by branch-selective mapping/tone and export. This agrees with REQ-PSF-004 and preserves the original branch.

Resolution evidence: `src/galaxy/pipeline.py`, existing dual-branch PSF tests, and [Phase 3 coverage](../testing/scene_pipeline_coverage.md).

## 2026-09-14 Phase 6 Render Isolation Review

### GAP-RENDER-001 Background Completion Can Replace Newer Draft Edits

Status: closed 2026-09-14.

A render worker launches from a saved input revision. Phase 5 initially installed
the worker's completed card directly into session state. If the user changed live
mapping, tone, frame, selection, or PSF inputs while the worker ran, that completion
could replace the newer draft. Replacing or closing the scene could also detach the
job before cooperative cancellation reached a terminal state.

Impact: newer unsaved inputs could be hidden or replaced, and a detached worker
could continue updating the prior scene file.

Resolution: Phase 6 merges immutable completion history into the live draft while
preserving newer effective inputs and stale-preview semantics. Replacement and
close request cancellation and wait for a terminal worker state before detaching
the scene. Focused regressions cover merge persistence, scene-identity rejection,
and cancellation-before-departure.

## 2026-09-14 Phase 7 Atomic Render Commit Review

### GAP-RENDER-002 Worker Commit Uses Its Launch Snapshot as the Save Base

Status: closed 2026-09-14.

The background worker builds its completed scene from the launch snapshot. Before
Phase 7, its final save compared that snapshot-derived card to the current file but
did not merge with the current file. A concurrently saved title or description at
the same content revision could be replaced. A concurrently saved effective-input
edit advanced the revision and caused the render commit to fail instead of being
retained as stale history.

Impact: successfully produced render artifacts could be lost from history, or
same-revision scene metadata could be overwritten.

Resolution: Phase 7 added optimistic previous-document validation to scene saves.
The worker now reloads the latest saved scene, merges immutable render history into
that version, checks cancellation at the commit boundary, and rejects a second
intervening modification. Regression tests cover concurrent metadata preservation,
newer effective inputs with stale render history, and optimistic-save mismatch.

## 2026-09-14 Artifact Storage Specification

### GAP-STORAGE-001 Existing Artifact Layout Predates the Normative Contract

Status: open pending implementation.

Revision 1 of `docs/artifact_storage_spec.md` now defines the canonical scene key,
asset root, input, per-render branch, retained-export, and application-cache
layouts. Existing execution uses a flat `render-r<revision>-<token>` work directory
with per-run `cache/` and `reprojected/` children, so it does not yet produce the
new canonical layout.

Impact: current artifacts remain safe and traceable, but their locations and names
are implementation conventions rather than the new durable storage contract.

Next action: implement the storage path builders and manifest fields, migrate all
artifact producers and consumers, add layout/containment/immutability tests, and
close this gap only after repository-wide verification. Existing artifacts shall
not be silently moved.

## 2026-09-15 First Human UI Flow Readiness

### GAP-HUMAN-001 Bundled Example Human Acceptance Pending

Status: implementation complete; open pending manual AC-HUMAN-001 signoff.

The normal project selector now lists `artifacts/Pillars.json` under Examples,
opens it with protected origin state, displays a verified scene-card-derived
artifact inventory, and saves edits only as a new user scene. Offline domain and
Streamlit tests cover discovery, exact inventory, unreferenced-file exclusion,
missing/corrupt distinctions, current/stale renders, path deduplication, and source
preservation during copy-on-save.

Remaining impact: automated entry criteria pass, but the visual and interaction
steps have not yet received human signoff.

Human test observation, 2026-09-16: Edge required two separated clicks to activate
almost every tested radio button or checkbox. A controlled Chromium run accepted a
workflow radio change after one click. Remediation assigns stable explicit keys to
radio and checkbox widgets, removes the changing navigation `index`, and logs each
received widget change. Automated single-activation coverage and a renewed Edge
human test are required before this gap can close.

Next action: execute the manual procedure in
`docs/compliance_status/human_test_readiness_revision_plan.md` and close this gap
after `AC-HUMAN-001` passes.

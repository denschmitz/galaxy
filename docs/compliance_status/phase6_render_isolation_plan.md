# Phase 6 Render Isolation and Departure Safety Plan

Date: 2026-09-14.
Status: complete.

## Baseline

Phase 5 closed the planned feature gaps and introduced background rendering. A
post-closeout review against REQ-NAV-003, REQ-NAV-004, REQ-NAV-006,
REQ-RENDER-006 through REQ-RENDER-008, and REQ-CARD-009 through REQ-CARD-012
identified a concurrency gap: a completed worker could replace edits made after
launch, and scene replacement or close could detach a running job without first
reaching a cancellation boundary.

This phase does not implement any proposal listed in the limitations section of
the design requirements.

## Phases

1. **6A - requirements and regression design:** record the render-isolation gap
   and add deterministic tests for stale completion merge, identity rejection,
   cancellation-before-replacement, and cancellation-before-close.
2. **6B - completion merge:** merge successful render assets and immutable history
   into the live draft while preserving newer inputs and stale-preview semantics.
3. **6C - departure coordination:** request cancellation and hold scene replacement
   or close until the worker reaches a terminal state; preserve the user's ability
   to cancel the departure.
4. **6D - verification and closeout:** update traceability and the durable gap
   register, run focused and full tests, dependency checks, documentation checks,
   and `git diff --check`.

Any intermediary finding shall be closed or explicitly retained in the final
known-gap review.

## Result

- Added `merge_render_completion` to attach completed immutable assets, render
  history, and export history without replacing a newer live scene definition.
- Current-input completions retain their generated thumbnail; completions for an
  older input revision remain available as stale history without becoming the
  current preview.
- Scene replacement and close now request cooperative cancellation and remain on
  the active scene until the render job reports a terminal state. Users can cancel
  the pending departure while preserving the current scene.
- Terminal jobs are detached before a replacement is installed, preventing a
  completion from being applied to another scene identity.

## Verification

- Focused UI and scene-pipeline suite: 32 passed.
- Full deterministic suite: 196 passed; one opt-in public archive test skipped.
- Read-only syntax validation parsed 48 Python files.
- `pip check` and `git diff --check` passed.
- Final documentation consistency checks passed.

GAP-RENDER-001 is closed. No intermediary Phase 6 findings remain open.

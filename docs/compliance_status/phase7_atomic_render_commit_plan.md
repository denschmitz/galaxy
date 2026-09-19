# Phase 7 Atomic Render Commit Plan

Date: 2026-09-14.
Status: complete.

## Baseline

Phase 6 protects the in-memory draft when a background render completes. Review
against REQ-NAV-003, REQ-NAV-006, REQ-RENDER-006 through REQ-RENDER-008,
REQ-CARD-005, REQ-CARD-009, and REQ-CARD-012 identified a remaining filesystem
race. A worker still constructs its final card from the launch snapshot. A
same-revision metadata save can therefore be overwritten, while a newer saved
input revision causes the worker commit to fail instead of retaining the render
as stale history.

This phase addresses that confirmed gap only. Coverage percentage by itself is
not treated as a requirement, and deferred product proposals remain out of scope.

## Phases

1. **7A - regression contract:** add deterministic concurrent metadata and input
   save cases plus an optimistic-save mismatch case.
2. **7B - optimistic scene save:** allow callers to supply the exact previous
   document they observed and reject a write if the destination changed.
3. **7C - latest-card render merge:** reload the latest scene after processing,
   merge immutable completion history into it, and commit against that observed
   version so concurrent metadata and newer inputs survive.
4. **7D - verification and closeout:** update traceability and the gap register;
   run focused/full tests, syntax, dependency, documentation, and diff checks.

Every intermediary finding shall be closed or explicitly retained in the final
known-gap review.

## Result

`save_scene` now accepts an optional exact previous document and rejects the
commit when the destination has changed since that document was read. The scene
pipeline reloads the latest saved scene after processing, merges immutable render
history and assets into it, checks cancellation once more at the commit boundary,
and performs the final save against that observed version.

Regression coverage demonstrates that a concurrent title edit survives the render
commit and that a concurrent effective-input edit advances the scene while keeping
the completed render as stale history. A second intervening save is rejected by the
optimistic previous-document check.

## Verification

- Focused scene-card and scene-pipeline suite: 84 passed.
- Repository-wide suite: 199 passed, 1 skipped (opt-in live archive test).
- Python syntax validation: 48 files parsed successfully.
- Dependency consistency: `pip check` reported no broken requirements.
- Patch hygiene and documentation consistency checks passed.
- `GAP-RENDER-002` is closed; no Phase 7 intermediary gaps remain open.

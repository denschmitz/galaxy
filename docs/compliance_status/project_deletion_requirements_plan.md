# Project Deletion Requirements Plan

## Scope

Define the missing Saved scenes workflow for deleting a user-owned Galaxy project.
This plan began as the requirements pass and now records the completed runtime
implementation and automated acceptance closeout.

## Phases

1. **Existing-contract review:** identify the scene-card and associated asset-root
   ownership boundary and the separate application-cache, bundled-example, and
   external-export domains.
2. **Behavior requirements:** define availability, protection, confirmation,
   deletion scope, recoverability, operation guards, and completion/failure state.
3. **Acceptance traceability:** add deterministic confirmation, isolation,
   rollback, active-operation, active-scene, and library-refresh scenarios.
4. **Closeout:** record the implementation gap and verify requirement identifiers,
   document references, and formatting.
5. **Implementation:** add the Saved scenes Delete action, explicit confirmation,
   recoverable card-and-asset-root transaction, rollback, active-render guard,
   active-scene closure, and filesystem-derived refresh.
6. **Verification:** exercise success, cancellation, bundled-example protection,
   isolation, rollback, and the Streamlit interaction; run the complete offline
   suite and close the gap.

## Exit Criteria

- Project deletion has atomic, testable requirements with unique identifiers.
- The deletion boundary includes the selected scene card and its associated asset
  root, but excludes caches, external exports, bundled examples, and other scenes.
- Cancellation, partial failure, active work, success, and recovery are specified.
- Acceptance coverage exists for the destructive transaction and visible workflow.

## Closeout

Implementation completed on 2026-09-24. `scene_workflow.delete_library_scene`
moves the validated user card and canonical associated asset root into a unique
`.galaxy-trash` transaction with a recovery manifest and rollback. The Saved scenes
row now exposes an Open-style Delete button, exact-scope confirmation, active-render
guard, success/failure state, active-scene closure, and refreshed library listing.
Focused transaction and Streamlit tests pass. GAP-DELETE-001 is closed; no
intermediary gap from this plan remains.

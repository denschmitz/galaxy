# Phase 2 — Scene Card Model and Persistence

Status: implemented and verified. Scope: JSON model/schema, draft/readiness validation, safe persistence, duplication, and isolated one-time legacy translation. Pipeline and CLI cutover were completed in Phase 3; UI cutover belongs to Phase 4.

## Phase 2A — Contract and baseline

Reviewed the current local scene-card schema, existing YAML model, Phase 1 changes, and known gaps. The previously proposed Phase 0 review was not applied. Preserve current requirement identifiers and document any implementation-critical clarifications here and in the schema before implementation.

Accepted migration policy: translate existing legacy projects to new JSON cards, preserve originals, verify each translation, then remove Galaxy-owned YAML support at cutover. Do not remove loaders while current pipeline/UI consumers still require them.

## Phase 2B — Model and persistence

Planned: strict draft models, generated JSON Schema, action readiness, reference validation, atomic save, immutable history, revision-safe edits, independent duplication, and temporary migration adapter.

## Phase 2C — Verification and closeout

Completed with strict model/schema parity, atomic persistence, immutable history, revision-safe edits, dependency reporting, independent duplication, and isolated legacy translation. The focused scene-card and migration suite passed 77 tests after final Phase 2 additions.

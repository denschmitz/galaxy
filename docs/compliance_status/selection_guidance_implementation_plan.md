# Guided Candidate Selection Implementation Plan

Date: 2026-09-22.
Status: complete and verified 2026-09-22.

## Objective

Implement REQ-DATA-010 through REQ-DATA-011, REQ-MAN-004 through REQ-MAN-006,
REQ-REFINE-019 through REQ-REFINE-032, and REQ-SELECT-009 through REQ-SELECT-015
without changing existing source preservation, explicit-Apply, or exact-product-pin
contracts.

## Phase A — candidate normalization

- Define the authoritative product-identity helper.
- Consolidate duplicate query rows before ranking and persistence.
- Preserve ranking-relevant metadata conflicts explicitly.
- Add focused normalization, conflict, ordering, and identity tests.

Exit: normalized manifests contain one record per authoritative identity and produce
deterministic conflict results.

## Phase B — manifest association and restoration

- Persist the normalized query result as a candidate-manifest scene asset.
- Associate it with the active draft before recommendation application.
- Restore available manifests without a network query.
- Report missing, corrupt, and stale manifests distinctly.

Exit: saving before Apply retains a verifiable route back to the exact candidate
set and recommendation state.

## Phase C — selection guidance domain behavior

- Implement preview-set, one-per-filter, and custom modes.
- Apply all, HST-only, and JWST-only scopes.
- Compute unique summary counts and known/unknown download sizes.
- Produce structured explanation facts independently of UI rendering.

Exit: every mode, scope, summary, and explanation is deterministic under offline
fixtures.

## Phase D — refinement UI

- Replace the flat primary table with grouped recommended rows and expandable
  alternatives.
- Add mode, scope, clear, restore, summary, and explicit Apply controls.
- Render explanations using the concise grammar in the normative specification.
- Replace the pre-application schema dump with workflow-stage guidance and move raw
  diagnostics under `Technical readiness details`.

Exit: the Streamlit flow satisfies the UI portions of AC-SELECT-GUIDANCE through
single-activation tests and visual inspection.

## Phase E — closeout

- Run focused normalization, selection, persistence, and Streamlit tests.
- Run the complete offline suite.
- Validate requirement identifiers, documentation links, JSON schemas/examples,
  and `git diff --check`.
- Reconcile every Phase A through D gap in `known_gaps.md`.

Exit: AC-SELECT-GUIDANCE passes, no intermediary gap remains open without an
explicit disposition, and GAP-GUIDANCE-001 is closed with verification evidence.

## Closeout

Phases A through D are complete. Candidate manifests now consolidate authoritative
download identities, preserve metadata conflicts, persist as scene-owned assets,
restore without a query, and carry deterministic mode, scope, and custom-selection
state. Refinement presents the exact bounded modes, unique-count summary, grouped
recommended rows, explicit alternatives, concise explanations, clear/restore
controls, explicit Apply, ordered workflow guidance, and a separate technical
readiness disclosure.

Phase E verification completed with 62 focused MAST/UI/selection tests passing,
followed by the complete offline suite with 238 passed and one opt-in live-archive
test skipped. Requirement-link checks and `git diff --check` are recorded in the
final validation for this pass. GAP-GUIDANCE-001 is closed; no intermediary gap
from this plan remains open.

# Remaining-work register review

Date: 2026-10-07. Scope: titles, presentation bridge, and selected P2 work; not an exhaustive requirement audit.

## Phase 0: baseline (complete)
Read known_gaps.md, the processing upgrade and bridge plans, normative requirements,
UI and processing coverage, and title/clone implementation. Preserve existing edits.

## Phase 1: reconcile (complete)
- GAP-TITLE-001 correctly tracks REQ-LIB-027..034 as unimplemented. Output-screen title editing exists; Saved-scenes inline rename does not. Added the missing coverage row.
- GAP-REPROJECT-BRIDGE-001 correctly remains open. Its introductory range is historical; updated it to 001..021, consistent with the existing dated update and coverage. Algorithm/default validation remains Phase 1 work.
- Phase 7 correctly awaits explicit selection. The 20 proposals are classified across P0/P1/P2/P3 in presentation_feature_assessment.md; they are not 20 accepted P2 requirements. Added a register pointer without selecting algorithms.
- GAP-HUMAN-001, GAP-BG-001, and GAP-COMP-002 remain separate acceptance/investigation/proposal dispositions.

## Phase 2: closeout (complete within scope)
The identified register/coverage omissions are reconciled. No runtime requirement is
closed by this documentation pass. Bridge and title implementation remain pending;
Phase 7 remains selection-gated. No implementation tests were run. Local references and `git diff --check` passed. This is not certification of all repository requirements.

Next: complete reprojection_bridge_plan.md Phase 1 contract/algorithm validation.

## Session handoff and validation evidence

Objective: reconcile tracking for titles, NaN presentation bridging, and Phase 7.
Changes: this phased review record; requirement-range correction and Phase 7
pointer in [known gaps](known_gaps.md); missing title coverage row in
[UI coverage](../testing/ui_scene_coverage.md). No runtime or normative contract change.

Commands/results:
- `git diff --check`: exit 0; existing LF/CRLF conversion warnings only.
- Inline Python via `.venv/Scripts/python.exe -`: reread the three affected
  records and asserted each relative Markdown-link target in the reviewed content
  exists; exit 0, `Affected local references verified.`
- Runtime pytest: not run; documentation-only tracking changes.

Review phases 0-2 are complete within the declared scope. No review finding remains
unresolved. Outstanding implementation is retained as GAP-TITLE-001 and
GAP-REPROJECT-BRIDGE-001 (including BR-F01..05); Phase 7 awaits selection. This
review does not certify repository-wide requirements compliance.

Next owner: [bridge development plan](reprojection_bridge_plan.md), Phase 1.
Title implementation remains owned by GAP-TITLE-001 pending its implementation
plan. The suggested bridge -> titles -> P2 order has not been adopted as a new
implementation mandate. Preserve all pre-existing checkout changes.

# Scene Workflow Requirements Pass

Date: 2026-09-10. Scope: documentation only.

## Phase 1 - Baseline and contract reconciliation

Status: complete.

Reviewed the requirements, known gaps, configuration model, UI entry logic, archive interface, and mapping implementation. Working tree was initially clean. The existing implementation uses YAML project files; the clarified target is a single JSON scene card that owns project settings and expands with artifact records.

Decisions:
- Scene card is the canonical project concept, not a wrapper referencing another project file.
- Binary assets may live in an associated folder or shared immutable source cache.
- Drafts may be saved before inputs are complete; readiness is derived for each action.
- Normal launch opens Discovery. Explicit artifact inputs retain defined routing.
- Existing requirement IDs are retained, including historical REQ-PROJ labels.
- Earlier unaccepted discovery ideas remain proposals.

## Phase 2 - Specification

Status: complete.

Created the canonical [requirements](../design_requirements.md) organized by purpose/definitions, externally driven scope, interfaces and sources, persistence, screen behavior, processing, architecture, and verification. The former hyphenated filename is now a compatibility link.

Created [five screen flows](../user_flows.md) and the [preliminary scene-card schema](../scene_card_schema.md), including required/optional fields, progressive completion, action readiness, binary references, render snapshots/history, and save semantics. No separate YAML scene settings document remains in the target design.

Created [acceptance traceability](../testing/ui_scene_coverage.md). Application tests are explicitly pending; existing YAML tests cannot certify JSON behavior.

## Phase 3 - Verification and closeout

Status: complete.

Verification results:
- All 200 requirement definitions have unique IDs; all 122 historical IDs are retained and 78 new IDs are defined.
- Every new requirement appears in the acceptance coverage matrix; application acceptance scenarios remain explicitly pending.
- All five user-flow sections are present, and all requirement references and inclusive ID ranges resolve.
- Both JSON examples parse; the complete minimal example contains all seven required metadata fields and the scene-card type/version markers.
- No obsolete project_ref/YAML-sidecar contract remains in the preliminary schema.
- All relative Markdown file links and all existing source/test paths listed in the coverage matrix resolve.
- git diff --check passed for tracked changes; new documents were also checked for unfinished content markers.
- No application code changed and no application pytest suite was run. Documentation checks do not certify runtime behavior.

Closeout dispositions:
- Filename mismatch: resolved with canonical underscore filename and compatibility link.
- Missing compliance directory: resolved; the existing durable directory is maintained.
- Scene-card JSON implementation and legacy migration policy: carried forward as GAP-SCENE-001.
- Five-screen workflow and acceptance tests: carried forward as GAP-UI-001.
- Pre-existing PSF/pipeline order conflict: carried forward as GAP-ARCH-001.
- Existing external-discovery adapter/UI gap: remains GAP-DISC-001.
- Temporary wrapper/project interpretation: superseded by the clarified single-card schema; no companion project_ref contract was published.

These explicit dispositions close this pass's intermediate work list. Open implementation work remains in the durable gap register; documentation completion must not be reported as software compliance.

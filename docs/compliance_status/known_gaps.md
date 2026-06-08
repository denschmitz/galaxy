# Known Gaps

This file tracks open compliance and implementation gaps identified during review and design passes.

## 2026-06-08 Multi-Method Discovery Phase 0 Baseline

Status: open

### GAP-DOC-001 Source Of Truth Filename Mismatch

The repository instruction says the project source of truth is `docs/design_requirements.md`, but the current requirements file is `docs/design-requirements.md`.

Impact: future agents may look for the wrong requirements file before implementation or review work.

Next action: decide whether to rename the file, add a compatibility copy, or update the repository instruction.

### GAP-COMP-001 Missing Compliance Status Directory

No existing `docs/compliance_status/` records were present at the start of this review pass.

Impact: prior review findings and deferred compliance items may not be discoverable.

Next action: maintain this file as the durable gap register for future passes.

### GAP-DISC-001 Multi-Method Discovery Not Yet Implemented

The accepted requirements for multi-method discovery define behavior for external discovery hints, including the Yuval Harpaz latest JWST release tracker. The Phase 2 model layer exists, including discovery hints, discovery source queries, source protocol, and hint alignment rotation, but adapters and UI integration do not exist yet.

Impact: users cannot yet retrieve JWST scene opportunities through external tracker hints inside Galaxy.

Next action: implement discovery-source adapters, hint-to-project conversion, UI workflow, adapter failure isolation tests, and end-to-end traceability in later phases.

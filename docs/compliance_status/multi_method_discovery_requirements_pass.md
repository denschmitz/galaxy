# Multi-Method Discovery Requirements Pass

Date: 2026-06-08

## Scope

This pass covers Phase 0 and Phase 1 for using the Yuval Harpaz latest JWST release tracker as one method among multiple user discovery methods.

## Phase 0 Baseline

Status: complete

Actions:

- Checked the current requirements source file.
- Checked for existing compliance status records.
- Created `docs/compliance_status/known_gaps.md`.
- Recorded source-of-truth filename mismatch, missing prior compliance records, and deferred multi-method discovery implementation.

## Phase 1 Requirements

Status: complete

Actions:

- Added accepted multi-method discovery requirements to `docs/design-requirements.md`.
- Preserved MAST as the authoritative product metadata and candidate manifest source.
- Defined external tracker records as discovery hints rather than archive product manifests.
- Added source provenance and failure isolation requirements for external discovery sources.
- Added the Yuval Harpaz latest JWST release tracker as a supported external discovery hint source.

## Deferred Work

Status: tracked

Deferred work is tracked in `docs/compliance_status/known_gaps.md` under `GAP-DISC-001`.

## Phase 2 Discovery Source Model

Status: complete

Actions:

- Added `src/galaxy/discovery_sources.py`.
- Defined `DiscoveryHint` as separate from archive candidate records.
- Defined `DiscoverySourceQuery` for source-specific discovery requests.
- Defined a `DiscoverySource` protocol for future adapters.
- Added `DiscoveryAlignment` with rotation values from 0 degrees through 360 degrees inclusive.
- Defaulted omitted discovery-hint alignment to 0 degrees.
- Treated 0-degree and 360-degree rotations as no-op alignments.
- Added focused tests in `tests/test_discovery_sources.py`.
- Added traceability in `docs/testing/discovery_source_coverage.md`.

Verification:

- `.venv` test command passed: `python -m pytest tests\test_discovery_sources.py`.
- A broader targeted run including `tests\test_config.py` was attempted, but `tests\conftest.py` failed while creating a temporary directory under `.tmp_test_cli` due to a workspace permission error before exercising config assertions.

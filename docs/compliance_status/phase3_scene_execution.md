# Phase 3 — Scene-Card Pipeline and CLI Cutover

Status: implemented and verified.

## Contract review

The image-processing requirements are grouped in section 6 of the canonical requirements. REQ-ARCH-001 now agrees with REQ-PSF-004: optional PSF processing operates on a derived native-frame branch before original and processed branches are reprojected independently. Exact selected product IDs remain authoritative.

## Implementation

- Added YAML-independent processing models and a scene-to-execution adapter.
- Added a canonical scene pipeline entrypoint that freezes the launch revision, uses exact pins, supports local source assets or authoritative MAST URIs, validates actual FITS plane/filter identities, confines generated assets to an associated directory, and appends successful render history atomically.
- The normal CLI now uses `--scene`, validates JSON scene cards, performs discovery from scene search inputs, and rejects legacy YAML command forms.
- Processing modules no longer import the YAML loader. Temporary translation remains isolated. The Phase 4 UI retains legacy compatibility until its cutover.
- Successful pipeline results record image, provenance, aligned-plane, and footprint assets. Failed inspection or processing does not publish a render record.

## Verification

- `tests/test_scene_pipeline.py`: 9 passed.
- Processing regression subset: 33 passed.
- Full repository suite: 196 passed, 1 skipped (opt-in live archive integration).

No live MAST request was required. A tiny local WCS FITS fixture exercises the canonical pipeline through composition and scene-card history commit.

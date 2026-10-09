# Pillars JWST Selection Remediation Plan

Date: 2026-09-20
Status: complete

## Objective

Replace the Pillars example's non-overlapping JWST detector products with the
authoritative Level-3 association mosaics, prevent the automatic selector from
repeating that error, and reject selected FITS planes whose measured WCS footprint
does not overlap the configured canvas.

## Phase 1 — Requirements and traceability

- Define parent-observation grouping and association-mosaic preference.
- Define deterministic `deepest_per_filter` behavior for unknown exposure times.
- Define the measured zero-overlap render failure.
- Add implementation and verification mappings to the coverage matrix.

Exit criterion: each behavior has an atomic requirement and planned test.

## Phase 2 — Selection and overlap implementation

- Propagate observation metadata through `parent_obsid` when MAST product rows do
  not repeat the observation identifier.
- Prefer combined Level-3 imaging products over their detector/exposure components
  within the same parent observation and filter.
- Rank known exposure time ahead of unknown exposure time for the deepest policy.
- Fail before composition when any selected reprojected plane has zero measured
  footprint coverage.

Exit criterion: focused deterministic tests pass without network access.

## Phase 3 — Example correction

- Pin the three program-2739 Observation-1 Level-3 NIRCam mosaics for F090W,
  F200W, and F444W.
- Remove cached-asset references to the obsolete detector products from the user
  scene while retaining valid HST selections.
- Validate the example and user scene cards.

Exit criterion: neither scene selects the NRCA4/NRCALONG component products.

## Phase 4 — Acquisition and render validation

- Download the public association mosaics to user-owned storage.
- Verify checksums, FITS readability, WCS overlap, and nonzero reprojection
  footprints before accepting a new render.
- Render the corrected six-filter scene and inspect its current thumbnail.

Exit criterion: all six selected filters contribute nonzero coverage, or the run
stops with an exact product diagnostic.

## Phase 5 — Cleanup and closeout

- Remove the obsolete JWST detector FITS files and derivatives authorized by the
  user, but preserve valid HST sources until the corrected render is verified.
- Remove abandoned partial downloads or failed work directories.
- Run the full offline suite, close resolved gaps, and record any remaining issue.

Exit criterion: no obsolete detector binary or same-stem reprojection/footprint
artifact is retained, tests pass, and the gap register reflects the final state.

## Closeout

- Phases 1 and 2 added and verified parent-observation grouping, Level-3 mosaic
  preference, explicit unknown-depth handling, and measured zero-coverage failure.
- Phase 3 corrected both the bundled example and its user copy. The user copy
  advanced to revision 4 when six local source-asset references were registered.
- Phase 4 downloaded and checksum-registered the three current MAST mosaics. The
  corrected six-filter scene rendered successfully as `render-r4-19f0904653aa`.
- Phase 5 removed 30 exact obsolete detector FITS, reprojection, and footprint
  files. Mixed HST composites and investigation evidence were intentionally kept.
- `GAP-FITS-001` remains open because HST DRC WHT/CTX validity masking is an
  independent issue.

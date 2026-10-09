# Selected-Footprint Viewport Requirements Plan

## Scope

Define the missing initial-canvas behavior exposed by a three-filter Horsehead
Nebula JWST scene whose target-centered search canvas showed only a small part of
the selected scans. This pass changes requirements, specification, flow,
acceptance traceability, implementation, and closeout status.

## Phases

1. **Contract review:** reconcile target/search-region framing, selected-product
   footprints, user-frame preservation, reprojection, and existing limitations.
2. **Geometry requirements:** define valid FITS footprint extraction, spherical
   union, deterministic tight framing, padding, scale bounds, and TAN feasibility.
3. **Interaction and warnings:** define first-render fitting, explicit later fits,
   preservation after user acceptance, and measured warnings for suspicious unions.
4. **Acceptance and closeout:** add offline WCS cases, record the implementation
   gap, and verify requirement references and document links.
5. **Implementation:** derive valid masked support boundaries, perform spherical
   TAN fitting and deterministic minimum-area orientation, cap preview dimensions,
   expose preview/apply/keep controls, and persist warning-free first-render fits.
6. **Verification:** exercise overlap, rotation, RA zero, invalid support,
   disconnected/extreme warnings, automatic persistence, manual preview/apply,
   and the real three-file Horsehead selection; close all intermediary gaps.

## Exit Criteria

- A new scene's initial rendered canvas is required to contain all selected valid
  FITS footprints rather than only the target search region.
- The fitted view is tight, padded, deterministic, and preview-size bounded without
  requiring a particular sky or instrument rotation.
- Disconnected or extreme selections produce quantitative warnings and choices.
- Missing WCS and infeasible one-canvas cases fail explicitly without omitting a
  selected scan.
- AC-FRAME-FIT has deterministic offline automated coverage and measured
  Horsehead evidence.

## Closeout

Implementation completed on 2026-09-24. `viewport_framing.py` fits the union of
selected masked FITS supports on a feasible TAN plane, applies deterministic tight
orientation and padding, coarsens previews to 2048 pixels, verifies containment,
and emits component/span/fill/raster/memory diagnostics. Refinement previews a fit
before explicit Apply, while a warning-free provisional frame is materialized by
the first render and retained in scene history. The three Horsehead files fit into
a 2023 by 2048 canvas at 0.068156 arcsecond per pixel with one component and no
geometric warning. GAP-FRAME-001 is closed; no intermediary gap remains.

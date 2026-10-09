# Per-Plane Display Normalization Compliance Plan

Date: 2026-09-21
Status: complete

## Objective

Implement the first three corrective steps for heterogeneous HST/JWST display
composition without rebuilding or modifying the Pillars example during this pass.

## Phase 1 — Validity masks and native metadata

- Define `DQ`, `WHT`, and `CTX` invalid-pixel semantics.
- Capture native `BUNIT` and mask-source metadata from FITS products.
- Carry invalid pixels into reprojection coverage rather than treating them as
  valid zero-valued science samples.

## Phase 2 — Per-plane display normalization

- Add persisted normalization policy to mapping defaults and per-plane/filter
  mapping entries.
- Support backward-compatible native values and explicit robust percentile
  display normalization.
- Apply normalization before RGB weights and output-channel tone processing.
- Record effective black/white points, gain, valid coverage, and RGB contribution.

## Phase 3 — Inventory and user indication

- Add native unit, mask source, normalization settings, valid coverage, and RGB
  contribution fields to the plane inventory.
- Warn when multiple native units are mixed while any enabled plane remains in
  native mode.
- Cover the new fields and warning with deterministic tests.

## Follow-on Pillars adoption

After the first three phases passed review, apply the agreed robust normalization
policy to the bundled example and existing user copy, preserve the user's local
FITS assets and render history, rebuild the user scene, and inspect the effective
coverage and channel-contribution diagnostics.

## Closeout

- Phase 1 combines applicable `DQ`, `WHT`, and `CTX` invalidity, carries masks
  into reprojection coverage, and preserves `BUNIT` and mask provenance.
- Phase 2 adds backward-compatible `native` and explicit `percentile` policies,
  applies normalization before RGB weights, and records effective display and
  contribution diagnostics.
- Phase 3 expands the source-plane inventory and emits a nonblocking mixed-unit
  warning. The existing Pillars scene now reports its two native unit families.
- Verification: 134 focused tests passed; the complete offline suite reported
  226 passed and one opt-in live archive test skipped.
- The complete offline suite passed with 226 tests and one opt-in live archive
  test skipped immediately before the example rebuild.
- `examples/Pillars.json` revision 4 and the user-copy revision 5 use the same
  0.5/99.5-percentile, asinh-4, unit-gain defaults.
- `render-r5-0ca41ad81945` reused all six local FITS products, completed without
  display warnings, and recorded nonzero contribution from every plane.
- The formerly visible HST zero-weight bands are absent. The now-visible
  cross-instrument footprint boundary is tracked separately as `GAP-COMP-001`.

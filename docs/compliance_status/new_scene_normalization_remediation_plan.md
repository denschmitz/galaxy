# New-Scene Normalization Remediation Plan

## Scope

Newly materialized scene mappings currently omit display normalization and
therefore resolve to backward-compatible `native` mode. Positive calibrated sky
backgrounds are then stretched without a valid-pixel black-point subtraction.

## Phase 1 - Requirement and traceability

- Define an explicit robust normalization default for newly materialized scenes.
- Preserve `native` fallback behavior for older revision-one cards that omit the
  field.
- Add the requirement to the UI coverage matrix.

## Phase 2 - Implementation and regression coverage

- Persist 0.5/99.5-percentile, asinh-4, unit-gain normalization when the app
  creates a scene's initial mapping.
- Assert every persisted policy value in the default-materialization regression
  test.
- Carry per-channel valid coverage through composition and exclude uncovered
  pixels from output tone percentiles.
- Verify uncovered pixels remain zero after channel tone and saturation.

## Phase 3 - Horsehead migration and app render verification

- Update the current Horsehead scene through scene-card editing and persistence
  APIs rather than editing its JSON directly.
- Recompose the existing aligned planes through the canonical scene pipeline so
  no FITS download or reprojection is required.
- Inspect the generated image and provenance, verify the background black-point
  behavior, and close the remediation record with exact results.

# Phase 5 controlled-stretch evidence

Date: 2026-10-02

## Scope and result

Phase 5 implements the bounded REQ-TONE-002 through REQ-TONE-013 feature set:

- independent legacy tone remains the omitted-field compatibility behavior;
- shared-intensity tone applies one curve multiplier to RGB with explicit clip or
  per-pixel rescale gamut handling;
- `linear` provides an identity main stretch and the explicit single-main-stretch
  action changes per-plane display stretches to linear;
- auto-stretch is a deterministic, background-region-derived proposal that does
  not change a scene until Apply and persists its resolved values;
- forward GHS uses independently implemented version 3.0.4 equations with float64
  intermediates and validated parameters.

The Render interface exposes application mode, method-specific parameters, gamut
policy, the explicit preset, proposal Preview/Recompute and Apply. Effective scene
inputs and provenance contain applied settings and algorithm versions.

## Automated verification

The final offline suite reports 321 passed and one opt-in live archive test
skipped. The two non-failing warnings are the established pytest-cache access
warnings under the junction-backed checkout.

Focused verification covers legacy known-answer compatibility; positive RGB ratio
preservation; zero, signed and partial-support behavior; clip versus rescale;
published exponential-subtype values; GHS identity, monotonicity, continuity,
endpoints and four local-intensity branches; parameter rejection; deterministic
auto proposal and failure gates; explicit single-main preset; Streamlit controls;
Apply/save/reopen without re-estimation; stale-render behavior; JSON schema; and
provenance algorithm records.

## Retained real-scene candidates

`scripts/phase5_stretch_candidates.py` reused retained aligned FITS for mixed
Pillars, HST-only Pillars, JWST-only Pillars and Horsehead. It generated legacy,
shared-asinh, single-main-asinh and a fixed illustrative single-main-GHS candidate
without changing a scene card or retained render. `summary.json` contains exact
settings, supported-pixel counts, intensity percentiles, max-channel fractions and
uint16 value counts.

| Scene | Legacy median | Shared asinh median | Single-main asinh median | Illustrative GHS median |
| --- | ---: | ---: | ---: | ---: |
| Mixed Pillars | 11404.77 | 11116.34 | 7036.61 | 8368.42 |
| HST-only Pillars | 27466.01 | 28834.03 | 21113.42 | 39109.05 |
| JWST-only Pillars | 23920.39 | 25470.92 | 18902.75 | 33812.91 |
| Horsehead | 27483.91 | 28665.07 | 24761.96 | 27220.47 |

The fixed GHS recipe is diagnostic, not a new default or a visual recommendation.
Its high max-channel fraction in the single-mission cases demonstrates why method
parameters and rescale behavior must stay explicit. None of the evaluated scene
cards currently persists background regions, so real-scene auto proposals fail
with the specified actionable diagnostic; synthetic and save/reopen tests verify
the complete proposal path.

Artifacts:

- `artifacts/phase5-stretch/summary.json`
- `artifacts/phase5-stretch/Pillars/legacy.png`
- `artifacts/phase5-stretch/Pillars/shared-asinh.png`
- `artifacts/phase5-stretch/Pillars/single-main-asinh.png`
- `artifacts/phase5-stretch/Pillars/single-main-ghs.png`

## Disposition

Phase 5 is technically complete. Candidate selection remains a user presentation
choice; no new stretch is forced as the default. Integrated manual workflow
retesting remains assigned to Phase 6.

# Image-processing upgrade Phase 6 closeout

Date: 2026-10-03

## Completion statement

- **Automated implementation:** complete for Phases 0-6. The final offline suite
  reports 322 passed and one opt-in public-archive test skipped.
- **Retained real-scene verification:** complete for mixed Pillars, HST-only
  Pillars, JWST-only Pillars, and Horsehead numerical/presentation candidates.
  Horsehead background-region correctness remains explicitly qualified; the
  candidate was accepted as significantly better, not as physical calibration.
- **Integrated technical browser verification:** complete in an isolated Chromium
  session. Final user presentation acceptance and the historical Edge-specific
  AC-HUMAN-001 signoff remain pending and are not represented as automated proof.

Phase 7 remains gated on explicit P2 algorithm selection.

## Delivered capability

The completed upgrade carries values, validity, fractional coverage, WCS/grid,
units, branch and lineage through the processing path; corrects masked PSF and
angular-sampling behavior; validates reusable aligned checkpoints; unifies direct
and pipeline rendering; exports the selected branch's registered uint16 TIFF;
provides explicit background, coverage, locked-normalization, shared-intensity,
auto-stretch proposal and forward-GHS workflows; and persists effective settings,
diagnostics and provenance without silently changing legacy defaults.

Intentional corrections are the validity/mask, ratio-singularity, PSF sampling,
checkpoint-integrity, direct-preview support and high-depth export changes recorded
by COMPAT-001. New background, coverage and tone choices remain explicit.

## Automated verification

Commands run from the repository root:

```text
.venv\Scripts\python.exe -m pytest tests\test_discovery_cache.py tests\test_pipeline_modes.py -q -p no:cacheprovider
17 passed in 2.33s

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
322 passed, 1 skipped in 13.84s
```

The skipped case is `tests/test_integration_public.py`, whose live MAST access is
opt-in. It was not run and is not claimed as passing.

The suite covers the required adverse paths:

| Path | Evidence and retained-state assertion |
| --- | --- |
| Cancellation | scene-pipeline and worker-boundary tests reject success history and checkpoint registration after cancellation |
| Failed stage | invalid inspected planes and fail-fast/non-fail-fast load cases preserve the fail-loud boundary |
| Corrupt checkpoint | digest, producer-key, plane-summary and incompatible-grid tests reject reuse |
| Missing dependency | missing selected local source fails readiness with the exact asset path |
| Concurrent edit | metadata is preserved; changed effective inputs retain the completed render only as stale history |
| Export failure | stale/unrendered, missing-role and existing-destination cases fail without changing prior export history |
| Precision and branch | direct and external TIFF tests retain uint16 values and explicit original/deconvolved roles |
| Diagnostic identity | registered background diagnostics and overlays have diagnostic asset kinds and are not selected-product sources |

## Integrated browser exercise

The app was launched at `http://localhost:8502` with the isolated scene directory
`artifacts/phase6-ui-scenes`. The session:

1. opened Saved scenes from a normal launch;
2. found the bundled Pillars example once and materialized `Pillars.json` in the
   isolated library;
3. moved from Scene refinement to Render and adjust with one radio activation;
4. displayed the persisted mapping/tone, background-pedestal, coverage and locked-
   normalization controls;
5. attempted a preview, received a specific network/download failure in the
   restricted environment, and retained the usable saved scene;
6. verified that export without a current successful render was rejected
   independently of scene saving; and
7. returned to Saved scenes and reopened the isolated user copy.

The complete successful Preview/Apply/save/reopen/checkpoint-reuse sequences remain
covered by deterministic Streamlit and pipeline tests. The live failure was not
misreported as a cancellation success: the remote requests failed before the
cancellation request reached a safe boundary.

## Real-scene and output observations

Retained Phase 4 evidence contains union-output/common-tone candidates for mixed
Pillars, both single-mission Pillars copies, and Horsehead. Retained Phase 5
evidence contains legacy, shared-asinh, single-main-asinh and illustrative GHS
candidates for the same four scenes. No scene card or retained render was changed
by those candidate generators.

The Horsehead Phase 3 TIFF is uint16, shape `2048 x 2023 x 3`, with 65,535 distinct
sample values. The retained mixed-Pillars pipeline TIFF is uint16, shape
`5000 x 5000 x 3`, with all 65,536 sample values represented. This confirms the
high-depth pipeline result independently of the external-export copy tests.

## Runtime and memory observations

The Phase 0 suite was 250 passed, one failed and one skipped in 20.02 seconds. The
final suite is larger (322 passed and one skipped) and completed in 13.84 seconds
on the same project environment with pytest cache writes disabled. A separate
instrumented run completed in 13.10 seconds (14.01 seconds wall time) with an
observed peak of 284.7 MiB summed across Python processes started for that run.
This is a process working-set observation, not an array-level profiler or a bound
for a 5000-pixel real render. No material test-suite runtime regression was found,
and no speculative optimization layer was added.

## Gap reconciliation

| Item | Phase 6 disposition |
| --- | --- |
| GAP-STORAGE-002 | closed: revision 3 distinguishes canonical application cache, render-private scratch, optional managed exports and external delivery artifacts; placement tests added |
| GAP-BG-001 | durable qualified limitation: region correctness and physical interpretation remain open; delivered workflow and candidate are retained |
| GAP-COMP-002 | durable scope boundary: seamless full-union compensation/feathering was not authorized and is not claimed |
| GAP-HUMAN-001 | integrated Chromium verification complete; user Edge signoff remains the exact pending acceptance event |
| GAP-TITLE-001 | requirements-only lifecycle enhancement explicitly deferred by the user; no Phase 6 implementation or saved-scene mutation |

The stale Phase 4 coverage row and Phase 3-5 architecture inventory labels were
updated to implemented status. Delivered algorithm sections contain their selected
variant, equations, failure behavior, diagnostics and adaptation record; Phase 7
insertion points remain visibly deferred.

## P2 selection handoff

| Candidate | Selection work still required |
| --- | --- |
| Empirical PSF integration | qualify stars, centering, spatial adequacy, sampling, kernel assets and UI |
| Regularized RL / deringing | choose an objective/update, signed-input policy, convergence and halo/noise metrics |
| Residual registration | define source confidence, transform bounds, WCS/mask propagation and resampling |
| Same-band robust combination | define compatible identities/units/PSFs, ancestry, small-N and uncertainty behavior |
| Residual debanding | demonstrate stripes and valid detector/mosaic geometry before choosing a method |
| Wavelet denoising | define correlated-noise/support behavior and injected-feature acceptance |
| Masked highlight protection | define persisted masks and halo/transition limits; demonstrate need beyond GHS |
| Noise-based weighting | define comparable measurements, variance semantics and provenance first |

No P2 candidate is selected by this closeout.

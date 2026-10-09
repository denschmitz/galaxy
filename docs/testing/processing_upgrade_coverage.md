# Image-processing upgrade coverage matrix

Status: Phases 1 and 2 complete on 2026-09-28. Phase 3 complete on 2026-09-29;
Phases 4 and 5 complete on 2026-10-02; Phase 6 technical closeout complete on
2026-10-03;
human assessment found the Horsehead candidate significantly better while leaving
the background-region interpretation qualified. “Specified” is not implementation
evidence.

| Proposal / requirement | Architecture definition | Implementation | Verification | State |
| --- | --- | --- | --- | --- |
| P00-01 / REQ-IMG-001 | IMG-CONTRACT-001, MASK-001 | `FITSPlane`, `ReprojectedPlane`, mapping and PSF consumers | FITS mask combination, reprojection invalid-source, normalization invalid-support and masked-RL tests | automated complete |
| P00-02 / REQ-IMG-003 | IMG-CONTRACT-001 | `CompositionInputs`; typed package domains | `test_composition_rejects_display_domain_as_linear_input` | automated complete for active composition boundary |
| P00-03 / REQ-IMG-004 | IMG-CONTRACT-001, REPROJECT-001 | deterministic WCS/shape grid identity in FITS and reprojected packages | FITS WCS round trip, wrong-grid arithmetic, missing-WCS and false-grid-identity rejection | automated complete |
| P00-04 / REQ-IMG-005 | STAGE-001 | derived/mapping and PSF stages return new arrays | `test_derived_arithmetic_does_not_mutate_input_packages`; masked-input perturbation | automated complete for migrated stages |
| P00-05 / REQ-DERIVED-001..002 | ARITH-001 | `compute_derived_planes` returns full image packages | ratio singularity, wrong-grid rejection, nonzero-operand support and immutability tests | automated complete |
| REQ-IMG-002, REQ-IMG-006 | IMG-CONTRACT-001, MASK-001, NUM-001 | separate validity/coverage with constructor and consumer validation | invalid coverage, nonfinite usable value, celestial geometry and support-boundary tests | automated complete for migrated packages |
| P00-06 / REQ-CHK-001..003, 005..008 | CHECKPOINT-001, IDENTITY-001 | `checkpoints.py`; strict pipeline reuse; `artifact_paths.py` | canonical-key, invalidation, missing-manifest, renamed-pair, branch-layout and legacy-boundary tests | automated complete |
| P00-07 / REQ-CHK-004 | CHECKPOINT-001 | exact FITS byte count/digest and loaded plane/grid validation | corrupt FITS, self-inconsistent key, summary mismatch and incompatible-grid tests | automated complete |
| P00-08 effective settings | IDENTITY-001 | checkpoint producer inputs plus existing scene `effective_inputs` and stale guards | source/canvas/kernel invalidation; mapping/tone reuse; stale/concurrent/save/reopen tests | automated complete for Phase 2 settings |
| P00-09 / REQ-PROV-010 | PROV-001 | aligned checkpoint `stage_records` in provenance | requested/resolved settings, versions, lineage, branch, grid and output digest assertions | automated complete for aligned checkpoint stage |
| P00-10 / REQ-RENDER-010 | STAGE-001 | `rendering.render_aligned_planes` used by pipeline and direct preview | `test_pipeline_and_direct_preview_share_numerical_core_with_partial_support` | automated complete |
| REQ-COV-001 through REQ-COV-007 | COVERAGE-001 | coverage configuration and shared render-core support/crop implementation | synthetic union/common, missing-band, hole, disconnected, empty, padding, tone-invariance and WCS tests | automated complete; real-scene evidence complete |
| REQ-COV-008 | COVERAGE-001 | independent output-footprint and brightness-reference persistence plus Streamlit preview/Apply controls | scene round-trip, accepted-default, stale-render and UI interaction tests | automated complete; policy accepted 2026-10-02 |
| REQ-NORM-010 | NORM-REFERENCE-001 | fixed-bound plane normalization | bounds validation, exact scaling, constant/invalid values, legacy regression | automated complete |
| REQ-NORM-011 through REQ-NORM-013 | NORM-REFERENCE-001 | region proposal, locked reference persistence and explicit recompute | region mask, identity, clipping diagnostics, persistence and no-silent-recompute tests | automated complete |
| REQ-NORM-014 | NORM-REFERENCE-001 | Streamlit normalization workflow | preview/Apply/save/reopen and branch tests | automated complete; policy accepted 2026-10-02 |
| P00-11 / REQ-OUT-005, 007 | ENCODE-001 | registered high-depth TIFF role and fail-loud export | uint16 export with more than 256 distinct levels; missing-role rejection | automated complete |
| P00-12 / REQ-OUT-006 | ENCODE-001 | explicit original/deconvolved branch selection | deconvolved branch copies its own high-depth artifact byte-for-byte | automated complete |
| P00-13 legacy defaults | COMPAT-001 | typed normalization/RGB stages retain the frozen recipe | `test_frozen_phase0_legacy_recipe_matches_known_answer` at `rtol=atol=1e-6` | automated complete for Phase 1 |
| GAP-PSF-MASK-001 / REQ-PSF-010 | PSF-RL-001 | `src/galaxy/psf.py` | `test_masked_values_do_not_change_valid_richardson_lucy_output` | automated complete |
| GAP-PSF-SCALE-001 / REQ-PSF-011 | PSF-GAUSS-001 | `src/galaxy/psf.py` | angular-width and native-WCS scale regressions | automated complete |
| REQ-PSF-012 | PSF-RL-001 | `src/galaxy/psf.py` | `test_richardson_lucy_rejects_valid_negative_samples` | automated complete |
| GAP-BG-001 / REQ-BG-001..008, REQ-NORM-009 | BG-PED-001, NORM-BG-001 | `background.py`; processing/scene models; shared rendering core; pipeline diagnostics/provenance; Render UI | seeded estimator accuracy and signal preservation; invalid/outlier/insufficient/off cases; corrected-zero regression; checkpoint reuse; branch save/reopen; canonical render registration; Streamlit Preview/Apply; Horsehead candidate diagnostics | complete; candidate visually accepted as significantly better, region interpretation remains qualified |
| cross-instrument GAP-COMP-001 / REQ-COV-001..008 | COVERAGE-001 | `coverage.py`; scene models; shared rendering core; Preview/Apply UI | unequal-footprint, crop, WCS, persistence, stale-render and four-scene candidate verification | complete for accepted union-output/common-tone policy; seamless-union enhancement remains separately unselected |
| REQ-TONE-002..005, 013 | TONE-SHARED-001 | `tone.py`; tone models; Render controls and preset | legacy known answer; ratio, signed/zero, gamut, partial support, stale render and preset tests | automated complete; real-scene A/B retained |
| REQ-TONE-009..012 | AUTOSTRETCH-001 | `tone.propose_auto_stretch`; locked scene record; Preview/Recompute/Apply UI | identity and failure gates; deterministic placement; UI; Apply/save/reopen/no drift | automated complete; evaluated scenes correctly report missing persisted regions |
| REQ-TONE-006..008, 012 | TONE-GHS-001 | float64 forward GHS in `tone.py`; method-specific UI | published exponential vector; monotonicity, continuity, endpoints, identity, branch and validation tests | automated complete; illustrative A/B retained |

Baseline test evidence and fixture locations are recorded in
[`image_processing_upgrade_baseline.md`](../compliance_status/image_processing_upgrade_baseline.md).

Latest offline validation: 282 passed and one opt-in live archive test skipped on
2026-09-28. Focused Phase 1 contract integration reports 106 passed; the focused
Phase 2 path/pipeline/scene/UI suite reported 73 passed before the final acceptance
additions. All Phase 1 and Phase 2 rows are implemented and verified within their
documented scope.

Phase 3 focused evidence includes deterministic seed `20260928`, pedestal error
within `0.1` input-noise sigma, protected-source preservation within `1%`, explicit
insufficient-sample failure, exact off-mode identity, unsupported-pixel preservation,
and full Preview -> Apply persistence. Final offline validation on 2026-09-29:
290 passed and one opt-in live archive test skipped. Two non-failing warnings report
that pytest could not write its cache beneath the junction-backed checkout.

Phase 5 evidence is recorded in
[`phase5_stretch_evidence.md`](../compliance_status/phase5_stretch_evidence.md).
Final offline validation on 2026-10-02: 321 passed and one opt-in live archive test
skipped, with the same two non-failing pytest-cache warnings.

Phase 6 reran the complete suite with cache-provider writes disabled. Final counts
and integrated browser, failure-path, runtime, gap-disposition, and acceptance
evidence are recorded in
[`image_processing_upgrade_phase6_closeout.md`](../compliance_status/image_processing_upgrade_phase6_closeout.md).

## Historical reprojection bridge addition (2026-10-05)

| Requirements | Specification | Implementation | Verification | State |
| --- | --- | --- | --- | --- |
| REQ-BRIDGE-001..021; revised REQ-FITS-003 | reprojection_bridge_spec.md; reprojection_bridge_algorithm.md | Native bridge component implemented; pipeline integration pending | Native regressions and full-frame benchmark below | Open: GAP-REPROJECT-BRIDGE-001 |

### Bridge workflow review (2026-10-06)

Historical review: the previous REQ-BRIDGE-001..014 row was unimplemented; coverage extended
to REQ-BRIDGE-021. Existing 25 focused foundation tests passed; none proves bridge
implementation. The development plan owns the following new coverage:

| Requirements | Planned implementation | Required verification | Status |
|---|---|---|---|
| 001..003,005..011,015,021 | native preparation module, pipeline | eligibility, strict bypass, load timing, branch isolation, immutability, failure | Planned, missing |
| 012..014,018 | reprojection, planes, checkpoints, provenance | kernel influence, support round trip, stale/corrupt reuse, resource benchmarks | Planned, missing |
| 004,016..020 | models/schema, scene execution/workflow, UI | default/Off, save/reopen/duplicate, snapshot, stale preview, active-render lock, browser flow | Planned, missing |

All IDs above have prefix REQ-BRIDGE-. GAP-REPROJECT-BRIDGE-001 remains open.

## Historical native bridge implementation start (2026-10-07)

This section supersedes the earlier planned/missing native-code status. It does
not certify pipeline, persistence, checkpoint, branch execution, or UI integration.
Algorithm: [BRIDGE-MEDIAN-001](../reprojection_bridge_algorithm.md).
Evidence and exact commands: [active bridge plan](../compliance_status/reprojection_bridge_plan.md).

| Requirements | Implementation | Verification | Current boundary |
|---|---|---|---|
| REQ-BRIDGE-005..011 | `bridge.py`: typed profile, labeling/exterior exclusion, bounded local evidence, constant boundary median, immutable observation package | `test_bridge.py`: exact median; real hashed SCI/WHT/CON crop; signed/zero/nonfinite cases; exterior/diagonal/area/extent/edge/sample/noise/brightness/sector rejection; neighboring estimates excluded | Native component verified; render-path integration pending |
| REQ-BRIDGE-003 | `prepare_native_presentation(enabled=False)` passes original values/support, bypasses labeling | strict bypass regression; exact observations retained | Native Off verified; saved scene/pipeline switch pending |
| REQ-BRIDGE-012 | `NativePresentation` separates source validity, presentation support, native estimates | support identity and source preservation tests; actual interpolation and adaptive resampler experiments remove enlarged core | Native separation verified; aligned kernel-influence storage/transport pending |
| REQ-BRIDGE-013..014 | native diagnostics/profile identity and memory estimate; `benchmark_native_bridge.py` | full-size F090W: 171 candidate clusters, 71 accepted, 381 samples; resource evidence in active plan | Native counts/runtime/peak verified; producer keys, render provenance, reprojection budgets pending |
| REQ-BRIDGE-001..002,015..020; REQ-FITS-003 amendment | caller/pipeline, both branches, config/schema/history/UI, aligned FITS and checkpoint consumers | Required integration tests not implemented | Pending, not silently covered by native tests |
| REQ-BRIDGE-021 | native preparation failure wraps source identity and propagates | injected labeling and estimate failures; original source unchanged | Native failure verified; render skip-handler integration pending |

Native focused suite: 45 passed. Full-suite results are recorded in the active
plan after final validation. GAP-REPROJECT-BRIDGE-001 and BR-F01..05 remain open
for their unfulfilled integration/acceptance boundaries.


## Current bridge integration coverage (2026-10-08)

This table supersedes the historical pending rows above. Requirement IDs have
prefix REQ-BRIDGE-. Evidence and exact results are in the
[owning plan](../compliance_status/reprojection_bridge_plan.md).

| Requirements | Implementation | Verification | State |
|---|---|---|---|
| 001..003,005..011,015,021; REQ-FITS-003 amendment | `bridge.py`, source caller and independent PSF branch in `pipeline.py` | `test_bridge.py` native eligibility/strict bypass; `test_bridge_integration.py` real pipeline, raw PSF input, source hash, preparation failure outside skip handler, no-hole exact On/Off | Implemented and automated verified |
| 012 | `reprojection.py`, `mapping.py`, `background.py`, `coverage.py` | Both actual kernels transport positive influence; normalization/tone exclude estimates; derived ratios and zero-weight contributors; observation support unchanged | Implemented and automated verified |
| 013..014,018 | `planes.py`, `checkpoints.py`, `provenance.py`, conservative memory accounting | Single/stack FITS exact round trips including long IDs; missing masks and old manifests reject reuse; switch/version invalidation; full native input benchmark for both kernels | Implemented and automated verified |
| 004,016..017,019..020 | typed bridge models/schema, execution translation, effective inputs, scene workflow/readiness, `ui.py` | Default-On, explicit-Off, save/reopen/duplicate, historical snapshot stale, real-job save before preview, running lock, completion redraw, compose-only rejection; isolated browser save/reopen/render/export/stale export | Automated and technical browser verified; user full-scene signoff pending |

Native tests: 45. Integration tests: 20. Benchmark output is 512 x 512 from the
full native source. Retained source-crop PNG/TIFF artifacts were inspected. The
full mixed scene was not regenerated by this isolated QA pass. User presentation
acceptance remains GAP-REPROJECT-BRIDGE-001's sole open gate.

# NaN presentation bridge development and compliance plan

Updated: 2026-10-08. Pipeline/UI implementation and technical verification complete; user full-scene presentation acceptance pending.
Requirements: REQ-BRIDGE-001..021 and revised REQ-FITS-003.
Specification: `../reprojection_bridge_spec.md`.
Algorithm: [BRIDGE-MEDIAN-001](../reprojection_bridge_algorithm.md).

## Readiness decision and sequencing

The current code is ready for bounded bridge development. No new processing
framework or prerequisite P2 algorithm is necessary. Complete this plan after the
existing Phases 0-6 and before Phase 7 algorithm selection. The retained Phase 6
report records completed automated and real-scene work with user presentation
acceptance still pending; this pass does not certify that acceptance.

Historical baseline inspected seams (2026-10-06; superseded by final integration evidence below):

- `fitsio.load_fits_plane` and `FITSPlane` ingest SCI, DQ/WHT/CTX masks and preserve
  values, validity, coverage, WCS and identity. Keep this low-level loader strictly
  observational; invoke presentation preparation in its processing caller.
- `pipeline.py` loads selected source planes, builds native PSF companions, then
  independently calls `reproject_all` for both branches. Insert original-copy
  preparation after source loading/filter eligibility; keep raw planes for PSF.
  Prepare derived copies after PSF. Do not run bridging in metadata inspection.
- `reprojection.reproject_plane` presently forces masked samples to NaN. Merely
  filling values is insufficient: it would mask them again. Introduce separate
  presentation support while retaining observation validity, and transport kernel
  influence correctly for both adaptive and interpolation modes.
- `ReprojectedPlane`, `planes.py` stack export/load and single-plane aligned saves
  currently lack explicit estimate influence/presentation-support storage.
- `checkpoints.build_producer_inputs` already hashes upstream dependencies; add
  bridge settings/version and certify all new mask artifacts and their checksums.
- Scene models, schema, execution translation, input snapshots, provenance,
  readiness and Streamlit controls already provide integration patterns.

Baseline on 2026-10-06: `.venv/Scripts/python.exe -m pytest tests/test_fitsio.py
 tests/test_reprojection.py tests/test_planes_and_exports.py tests/test_checkpoints.py
 -q`: 25 passed. Pytest reported two cache-write permission warnings; test assertions
passed. This is focused foundation evidence, not bridge compliance or a full-suite
result. Checkout contains substantial pre-existing changes; preserve them.

## Phase 0 — requirements and readiness review (complete)

Reviewed current code, architecture, existing bridge proposals and known gaps.
Specified the saved switch, automatic load-time preparation, branch isolation,
stale-preview behavior, checkpoint reuse, render snapshots and failure handling.
GAP-REPROJECT-BRIDGE-001 remains open. GAP-FITS-001 and GAP-COMP-001 retain their
recorded dispositions; PNG alpha and broad cosmetic repair remain outside scope.

## Phase 1 — freeze algorithm and artifact contracts (complete)

Use the previous suggestions in the supporting specification as the starting
point: SciPy eight-connected labeling and border-label rejection, bounded local
bright-core evidence, then constant boundary-median filling as specified in BRIDGE-MEDIAN-001.
The harmonic suggestion is superseded by the recovered user preference for a flat core. Global adaptive ignore is insufficient
because it bypasses eligibility. Defer Gaussian/PSF fitting unless demonstrated
necessary and specified as a requirements amendment.

1. Verify installed dependency APIs and source fixture identities. Retain synthetic
   fixtures and the actual Pillars F090W six-pixel crop with hashes and coordinates.
2. Settle component limits, ring/annulus geometry, directional sector definitions,
   sample counts, tolerances, noise degeneracy and patch-edge rejection. Current
   native defaults are defined and verified in BRIDGE-MEDIAN-001; integrated
   acceptance remains pending.
3. Specify constant boundary-median reduction, precision, determinism and
   preparation failure. Confirm bounded estimates
   and preservation of finite valid zero and negative measurements.
4. Define native observation validity, repaired values/support, aligned observation
   support, presentation support and kernel influence separately. Specify influence
   propagation for both actual resamplers: nearest-neighbor mask reprojection alone
   cannot establish full kernel influence. Establish how background, normalization,
   derived combinations, PSF comparison, rendering and overlays consume these
   fields, ensuring estimates do not masquerade as observed statistical samples.
5. Specify field placement/defaults, FITS extension/header representation, missing
   extension behavior, checkpoint format/version migration and provenance schema.
6. Benchmark full-size mask labeling and both branch/method paths. Freeze runtime
   and peak-memory acceptance budgets with hardware, dimensions and measurement
   method. Include retained original/prepared copies and influence resampling.

Exit: update `image_processing_architecture.md`, bridge/checkpoint/scene schema
specifications and atomic requirements as needed; freeze known-answer cases and
numeric tolerances before production code. No further P2 selection is required.

## Phase 2 — native preparation implementation (complete)

Implement a small typed bridge module/result using NumPy and SciPy array operations.
Label once, reject border/oversized labels before patch-local evidence and estimation.
Loops over bounded components are acceptable; avoid full-grid distance transforms.
Return separate presentation values/support and estimate mask plus counts/reasons.
Integrate automatic original-copy preparation with selected-source processing;
retain observational inputs for PSF and prepare that branch independently.
Unexpected bridge errors must escape the FITS-load skip handler.

Add deterministic tests for eligible six-pixel holes, eight-connected exterior
paths, large/long clusters, dark/flat nebulosity, inadequate samples, noise
 degeneracy, edge patches, all-valid/all-invalid inputs, zeros/negatives, immutable
sources and preparation failure. Off bypasses detector/estimator and reproduces strict
processing. Exit: REQ-BRIDGE-001..011,015,021 numerical behavior passes.

## Phase 3 — resampling, persistence and downstream integration (complete)

Transport observation support, presentation support and actual resampling-kernel
estimate influence through both branches and both methods. Extend aligned save/load,
stack records, rendering inputs, provenance, checksums and memory accounting.
Include effective bridge configuration/version in producer dependency identity;
old or mismatched checkpoints require reprojection. Keep compose-only free of
native bridge execution. Verify mask corruption/missing masks and setting/version
changes reject reuse; valid round trips preserve values and support. Test derived
ratios and disabled/zero-weight bands against false support contamination.

Exit: REQ-BRIDGE-012..014,018 complete; persistence and downstream support contract
validated without changing observation validity.

## Phase 4 — saved switch and complete user flow (complete)

Add typed configuration and scene/schema fields, execution translation, effective
inputs, render history and the "Bridge small NaN holes" switch. Default absent to
On; preserve explicit Off. Expose no extra controls beyond the agreed switch.
Persist pending edits before launch, lock control during active rendering, and
identify stale results when toggled. Offer full/reproject-only rebuilding through
the existing workflow; do not silently reuse stale compose-only artifacts.

Test new/old scenes, both states, save/reopen/duplicate, history snapshots, edit
then Generate preview, compose-only rejection, active-render locking, and visible
help/staleness. Use actual Streamlit browser verification for the complete workflow,
not only unit mocks. Exit: REQ-BRIDGE-004,016..020 pass with retained UI evidence.

## Phase 5 — integrated acceptance and final gap closeout (technical complete; user acceptance pending)

Run focused tests then the full offline pytest suite from `.venv`; disable pytest
cache provider if junction permissions prevent cache writes. Retain real Pillars
On/Off A/B outputs and diagnostics. Off must reproduce strict holes; On must fill
the six-pixel case only if the frozen eligibility criteria accept it. If that target
fails, resolve detector/requirement mismatch explicitly before calling the feature
complete. Test representative HST/JWST no-hole scenes, both resampling methods,
both branches, save/load, compose-only and UI export after toggle.

Measure actual full-frame runtime/peak memory against Phase 1 budgets. Update the
coverage matrix per requirement, reconcile architecture/schema/user flows, and
close every intermediary finding from this plan. Required unresolved findings
block completion. Close GAP-REPROJECT-BRIDGE-001 only with numerical, persistence,
UI and real-scene evidence. Report automated completion, technical browser checks
and user presentation acceptance separately. Then resume Phase 7 P2 selection.

## Development findings to close in Phase 5

| ID | Required resolution | Current state |
|---|---|---|
| BR-F01 | Freeze detector/estimator and resource budgets | Closed: BRIDGE-MEDIAN-001 and BRIDGE-WIRE-002 frozen; both full-input resampling benchmarks pass |
| BR-F02 | Preserve observational inputs across load-time preparation and PSF | Closed: immutable source hashes and raw PSF inputs verified; preparation failures escape skip handler |
| BR-F03 | Persist support/influence including kernel transport and checkpoint integrity | Closed: both actual kernels, support FITS round trips, missing/corrupt support rejection, producer identity and strict reuse verified |
| BR-F04 | Saved switch, stale results and fixed render snapshot | Closed: default-On/explicit-Off, save/reopen/duplicate, snapshot, running lock, stale preview/export verified |
| BR-F05 | Full-frame, real-scene and complete UI verification | Technical evidence complete: full native input benchmarks, real crop On/Off, both branches, browser save/reopen/render/export. User full-scene acceptance remains an explicit gate |

## Historical restart instruction (superseded below)

Implement this plan through Phase 5 before returning to algorithm selection in
`image_processing_upgrade_implementation_plan.md` Phase 7. Verify current changes
and baseline first; freeze Phase 1 specification before production implementation.
Preserve unrelated work and source FITS. Record evidence and close all bridge
findings; do not mark requirements-only documentation as implemented behavior.

## Historical native-start handoff (2026-10-07)

Objective: specify the user-discussed algorithm, reference it from requirements,
and begin native numerical implementation. Prior chats confirm a flat boundary
median; no PSF reconstruction or unrelated P2 algorithm is selected.
Phase 1 native contract is defined in BRIDGE-MEDIAN-001. The full artifact/consumer
and resampling resource gates remain pending; no full Phase 1 exit is claimed.
Native code can be verified independently without connecting incomplete support
contracts to the production pipeline. Phase 2 native component is implemented and verified;
load-time wiring follows Phase 3 support integration rather than shipping fills
that the strict reprojection mask would immediately erase.

Fresh baseline: focused FITS/reprojection/plane/checkpoint command reports
25 passed outside the Windows sandbox. The sandboxed run reported 20 passed and
5 WinError 650 filesystem failures during rename. No assertions were changed.
Next: finish aligned support persistence and actual-kernel influence contracts,
resampling budgets, then implement Phase 3 support integration before pipeline/UI.

### Native implementation evidence

Changes: [algorithm](../reprojection_bridge_algorithm.md), normative references in
[requirements](../design_requirements.md), architecture/workflow-spec references,
`src/galaxy/bridge.py`, `tests/test_bridge.py`, exact hashed fixture under
`tests/fixtures/reprojection_bridge/`, and `scripts/benchmark_native_bridge.py`.
The existing production caller remains strict; bridge activation is not advertised
as available in the application. No scene, archived source, or historical asset
was rewritten. No unrelated pre-existing change was reverted.

Commands/results:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_fitsio.py tests/test_reprojection.py tests/test_planes_and_exports.py tests/test_checkpoints.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_bridge.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/benchmark_native_bridge.py --source artifacts/scenes/Pillars/inputs/sources/b4bbfe83bc6c0a5d7d5328d42961b78f43fdb5be61afe18edca1b98a8680cadb/jw02739-o001_t001_nircam_clear-f090w_i2d.fits --output artifacts/reprojection-bridge/native-f090w-benchmark.json
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Fresh baseline: 25 passed. Native regressions: 45 passed, including both actual
resampler numerical experiments. Initial test-data corrections retained exact
assertions: the two-pixel ring has 36 (not 38) samples and exact median 117.5;
the directional-rejection fixture now has three raised noisy annulus sectors,
so it tests directional rejection rather than a zero-MAD noise rejection.

Full native source: 8582 x 14340, 171 components, 71 accepted, 381 estimates,
1.166816 seconds. Process peak working set 2,946,416,640 bytes (2.744 GiB), within
the <=60-second / <=6-GiB resident budget. Estimated incremental working bound
2,954,673,728 bytes. Committed peak 8,310,333,440 bytes was already reached during
FITS loading and did not increase with preparation; it is not concealed by the
resident budget. The first benchmark compared the maximum of distinct resident
and committed metrics and reported failure; the reporter was corrected to the
explicit resident-memory acceptance metric, with both metrics retained. This
metric clarification changes no algorithm output, tests, or resource measurement.

Retained local evidence:
- `artifacts/reprojection-bridge/native-f090w-benchmark.json` (hardware, load baseline, counts, timing and memory).
- `artifacts/reprojection-bridge/native-core-evidence.npz` and `.json` (observation and presentation arrays/masks).
- `artifacts/reprojection-bridge/native-core-comparison.png` (identical scale, nearest sampling). Visually inspected: the six-pixel black core is replaced by a flat patch; observed surroundings are unchanged. This is native-crop technical evidence, not user acceptance or an integrated render.

Remaining findings: BR-F01 aligned/consumer contract and resampling budgets;
BR-F02 source-load/PSF caller wiring; BR-F03 persistence/kernel/checkpoint identity;
BR-F04 saved switch and complete flow; BR-F05 integrated/real-scene/UI acceptance.
No full bridge phase or GAP-REPROJECT-BRIDGE-001 is closed by the native start.

### Final native-start validation

Final commands are the focused/full pytest commands above, executed with `.venv`.
Final focused validation: 45 passed. Full offline validation outside the verified
sandbox rename limitation: 367 passed, 1 opt-in live test skipped, 3 non-failing
Astropy WCS warnings (15.35 seconds). Three non-failing Astropy
OBSGEO header-normalization warnings come from the retained exact celestial WCS;
the opt-in live archive test remains skipped. No required integration check is
claimed complete. Added a report-destination guard to prevent the benchmark
from overwriting its input, with an immutable-source regression.

Local Markdown references in all affected documents and the specimen checksum
passed. New Python modules parsed and return annotations were checked. Final
`git diff --check` passed (pre-existing LF/CRLF conversion warnings only). Native
code/specification and the retained comparison were inspected. Remaining findings
and the next Phase 3 prerequisite step are listed above; no new unowned work list
was created. The earlier remaining-work review remains a historical snapshot.

## Historical pipeline/UI integration start (2026-10-07)

User authorized pipeline integration and the UI component. BRIDGE-WIRE-002 now
freezes aligned fields, positive-kernel indicator transport, FITS/manifest versions,
legacy history/default semantics and integrated resource budgets before code.
Phases 3-4 are active; BR-F01..05 stay open until their numerical, persistence,
caller/branch, UI and integrated evidence is recorded. Baseline copies of affected
files are retained under artifacts/reprojection-bridge/integration-baseline to
inspect only this pass's delta and preserve pre-existing edits.


## Final pipeline/UI evidence and handoff (2026-10-08)

Objective implemented: automatic native presentation preparation for the original
branch after successful source ingestion, independent preparation after native PSF
processing, saved default-On UI switch, certified aligned support and compose-only
reuse. Low-level FITS observations and PSF inputs remain unmodified. BRIDGE-WIRE-002
was specified before integration code. Statistical consumers exclude every output
with positive estimate-kernel influence. Aligned FITS uses SUPVER=1; checkpoints
use format 2 and reject prior/mismatched support. Legacy scenes default On; legacy
render history without an explicit bridge snapshot remains historical and stale.

BR-F01..04 are closed. BR-F05 technical verification is complete; user acceptance
of the full scene remains pending. No numerical, persistence, caller or UI
implementation finding remains. GAP-REPROJECT-BRIDGE-001 stays open solely for
that separately recorded user presentation gate. No P2 method has been selected.

Retained evidence under `artifacts/reprojection-bridge/`:

- `integrated-interpolation-benchmark.json`: full 8582 x 14340 input, 512-square
  output, 2.494361 seconds, 3,075,731,456 bytes peak resident; 11 influenced outputs.
- `integrated-adaptive-benchmark.json`: same dimensions, 3.831400 seconds,
  3,606,810,624 bytes peak resident; 35 influenced outputs. Both satisfy the frozen
  <=120-second / <=16-GiB resident budget. This bounds the specified benchmark,
  not arbitrary output dimensions, numbers of bands or scenes.
- `integrated-scene-evidence/comparison.json` and linked PNG/TIFF/aligned FITS:
  six native estimates produce 12 influenced presentation outputs in the real
  retained crop; observational support remains exactly 4443 pixels On and Off.
  Both PNGs were visually inspected: On presents a filled core; Off retains the
  strict dark hole. These are specimen renders, not a rebuilt full mixed scene.
- `ui-verification/scene.json` and `verified-bridge.tiff`: isolated browser flow
  verified default On, Off save/reopen, On saved before Generate preview, successful
  history snapshot, TIFF export (67 x 68 x 3 uint16), and stale export rejection
  after toggling Off. In-app Chromium was available; Edge was unavailable. No
  user-owned scene was changed. User Edge/full-scene signoff is not claimed.
- `integration-baseline/`: pre-pass file copies permit review of only this pass
  while preserving the existing dirty checkout.

Browser verification exposed a completion-redraw defect: a successful job could
leave the prior placeholder until a second rerun. The completion handler now
reruns after merging the saved render, with an actual-job AppTest regression.
A long product identity round-trip regression also verifies untruncated PARENT
headers; the FITS long-card comment warning does not truncate the identity.
An initial full-suite failure identified an environment leak from a new AppTest;
the test now uses pytest monkeypatch so later UI cases retain their own settings.
No assertions were weakened.

Verification commands (project `.venv`, outside the documented Windows junction
rename restriction):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_bridge_integration.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/benchmark_bridge_integration.py --source artifacts/scenes/Pillars/inputs/sources/b4bbfe83bc6c0a5d7d5328d42961b78f43fdb5be61afe18edca1b98a8680cadb/jw02739-o001_t001_nircam_clear-f090w_i2d.fits --output artifacts/reprojection-bridge/integrated-interpolation-benchmark.json
.\.venv\Scripts\python.exe scripts/benchmark_bridge_integration.py --source artifacts/scenes/Pillars/inputs/sources/b4bbfe83bc6c0a5d7d5328d42961b78f43fdb5be61afe18edca1b98a8680cadb/jw02739-o001_t001_nircam_clear-f090w_i2d.fits --adaptive --output artifacts/reprojection-bridge/integrated-adaptive-benchmark.json
```

Focused integration: 20 passed, covering both kernels, original/native-PSF
branches, history, exact no-hole On/Off equivalence for HST/JWST-labelled cases,
source immutability, statistics, support persistence, reuse and UI. Telescope
no-hole cases use the retained crop with invalid samples repaired only in test
copies; they do not represent separate archival HST acquisitions. Full-suite
final result and diff/reference checks are recorded below after the last run.

Next user step: restart/reload the application, open the intended scene, leave
Scene refinement > Bridge small NaN holes On, then Generate preview. A PNG preview
is sufficient for visual acceptance; a final TIFF is optional. Existing aligned
checkpoints require a fresh reprojection once. Record full-scene acceptance here
and close GAP-REPROJECT-BRIDGE-001 before returning to Phase 7 selection.


### Final validation result

Final offline suite: **387 passed, 1 skipped** in 18.99 seconds. The skipped test
is the opt-in live archive check. Non-failing warnings are 31 Astropy OBSGEO
header-normalization notices from the retained WCS and one FITS long-card comment
truncation notice; the long identifier round trip passes exact equality. Final
focused integration: **20 passed**; the earlier combined UI/selection/integration
run passed 74 tests before adding four no-hole pipeline cases.

Local Markdown references, Python parsing and whitespace checks passed.
`git diff --check` passed (existing LF/CRLF conversion warnings only). The
pre-pass comparison was reviewed and retained as
`artifacts/reprojection-bridge/integration-pass.diff`; unrelated edits were
preserved. PNG On/Off and successful browser preview were visually inspected.
The successful browser screenshot is retained as
`ui-verification/preview-complete.png`. The successful preview redraw now occurs
on the completion refresh itself. The isolated verification server was stopped
after the flow; normal application sessions were not changed.

# Known Gaps

This file tracks open compliance and implementation gaps identified during review and design passes.

## 2026-06-08 Multi-Method Discovery Phase 0 Baseline

Status: closed 2026-09-14. All gaps recorded in this baseline have dispositions below.

### GAP-DOC-001 Source Of Truth Filename Mismatch

Status: closed 2026-09-10. The normative source of truth is now `docs/design_requirements.md`; `docs/design-requirements.md` is a compatibility link.

Impact: future agents may look for the wrong requirements file before implementation or review work.

Resolution: canonical filename now matches repository instructions without maintaining duplicate requirements.

### GAP-COMP-001 Missing Compliance Status Directory

Status: closed 2026-09-10. No compliance directory existed at the original baseline; the directory and durable gap register now exist.

Impact: prior review findings and deferred compliance items may not be discoverable.

Resolution: maintain this file as the durable gap register for future passes.

### GAP-DISC-001 Multi-Method Discovery Not Yet Implemented

Status: closed 2026-09-14.

The Yuval Harpaz CSV adapter, source attribution, offline filtering fixtures,
missing-thumbnail selection, isolated source failure behavior, and hint-to-scene/UI
conversion are implemented. MAST remains the authoritative product-discovery path.

## 2026-09-10 Scene Card and Screen Specification

### GAP-CONFIG-001 Application Storage Configuration Pending

Status: closed 2026-09-14.

Application configuration loading, initialization, and CLI/UI startup integration are
implemented. Phase 4 routes Saved scenes and default new-scene saves through the
effective scene directory.

Resolution evidence: src/galaxy/app_config.py, src/galaxy/scene_workflow.py,
src/galaxy/ui.py, tests/test_app_config.py, and tests/test_ui.py.

### GAP-SCENE-001 Canonical JSON Scene Card UI Integration Remaining

Status: closed 2026-09-14.

The strict JSON model, persistence, canonical pipeline, CLI, and five-screen UI use
scene cards. The normal UI/CLI reject legacy YAML and the pipeline no longer writes a
YAML sidecar.

Phase 5 removed the isolated translator, legacy loader, translated YAML originals,
PyYAML dependency, and legacy compatibility tests under REQ-MIG-006.

### GAP-UI-001 Five-Screen Workflow Not Verified

Status: closed 2026-09-14.

Discovery, Refinement, Render, Output/save, and Saved scenes are implemented over the
scene-card workflow layer. Offline tests cover JSON/FITS routing, target drafts,
selection pins, recommendations, frames, stale results, library isolation,
duplication, thumbnail creation, and guarded PNG/TIFF export.

Phase 5 added the external tracker gallery, explicit resolver outcomes and ambiguous
selection, a background render job with safe-boundary cancellation, operation-state
reporting, guarded active-scene close, and unsaved independent duplication.

### GAP-ARCH-001 Existing PSF Stage Ordering Conflict

Status: closed 2026-09-14.

REQ-ARCH-001 now places optional native-frame PSF processing on a separate derived branch before independent reprojection, followed by branch-selective mapping/tone and export. This agrees with REQ-PSF-004 and preserves the original branch.

Resolution evidence: `src/galaxy/pipeline.py`, existing dual-branch PSF tests, and [Phase 3 coverage](../testing/scene_pipeline_coverage.md).

## 2026-09-14 Phase 6 Render Isolation Review

### GAP-RENDER-001 Background Completion Can Replace Newer Draft Edits

Status: closed 2026-09-14.

A render worker launches from a saved input revision. Phase 5 initially installed
the worker's completed card directly into session state. If the user changed live
mapping, tone, frame, selection, or PSF inputs while the worker ran, that completion
could replace the newer draft. Replacing or closing the scene could also detach the
job before cooperative cancellation reached a terminal state.

Impact: newer unsaved inputs could be hidden or replaced, and a detached worker
could continue updating the prior scene file.

Resolution: Phase 6 merges immutable completion history into the live draft while
preserving newer effective inputs and stale-preview semantics. Replacement and
close request cancellation and wait for a terminal worker state before detaching
the scene. Focused regressions cover merge persistence, scene-identity rejection,
and cancellation-before-departure.

## 2026-09-14 Phase 7 Atomic Render Commit Review

### GAP-RENDER-002 Worker Commit Uses Its Launch Snapshot as the Save Base

Status: closed 2026-09-14.

The background worker builds its completed scene from the launch snapshot. Before
Phase 7, its final save compared that snapshot-derived card to the current file but
did not merge with the current file. A concurrently saved title or description at
the same content revision could be replaced. A concurrently saved effective-input
edit advanced the revision and caused the render commit to fail instead of being
retained as stale history.

Impact: successfully produced render artifacts could be lost from history, or
same-revision scene metadata could be overwritten.

Resolution: Phase 7 added optimistic previous-document validation to scene saves.
The worker now reloads the latest saved scene, merges immutable render history into
that version, checks cancellation at the commit boundary, and rejects a second
intervening modification. Regression tests cover concurrent metadata preservation,
newer effective inputs with stale render history, and optimistic-save mismatch.

## 2026-09-14 Artifact Storage Specification

### GAP-STORAGE-001 Existing Artifact Layout Predates the Normative Contract

Status: closed for the bounded Phase 2 branch-output scope on 2026-09-28.

Revision 2 of `docs/artifact_storage_spec.md` defines the canonical scene key,
asset root, input, per-render branch, retained-export and application-cache
layouts. New aligned planes, checkpoint manifests, individual aligned planes,
preview PNGs and high-depth TIFFs now use centralized canonical `original/` and
`deconvolved/` branch paths. Consumers prefer canonical paths and retain explicit
read-only support for historical flat names without moving those files.

Closure evidence: `src/galaxy/artifact_paths.py`, pipeline/scene registration,
direct-workdir discovery and `tests/test_artifact_paths.py` cover canonical path
construction, branch separation, bounded placement, canonical preference and
legacy preservation. Scene-pipeline tests verify actual new-run placement. The
complete offline suite reports 282 passed and one opt-in live test skipped.

Residual work not required by the Phase 2 checkpoint/diagnostic bound is recorded
as GAP-STORAGE-002 below.

### GAP-STORAGE-002 Input Cache and Managed Export Placement

Status: closed by Phase 6 contract reconciliation and verification on 2026-10-03.

The pipeline still uses its historical per-run `cache/` acquisition directory and
external exports are not always retained below the optional managed `exports/`
tree. This does not weaken the new checkpoint identity or registered render roles,
but it is narrower than the complete input/application-cache/managed-export layout
in `docs/artifact_storage_spec.md`.

Resolution: artifact-storage revision 3 distinguishes the canonical application
cache from render-private transient scratch. New discovery entries now use
`.galaxy-cache/candidates/`; remote bytes staged below a dedicated render's
`cache/` are explicitly unregistered scratch, not portable sources or shared-cache
claims. External exports remain authoritative user-selected destinations; a
scene-owned managed copy remains optional. REQ-CACHE-005 and REQ-CARD-018 through
REQ-CARD-019 make these boundaries testable. Placement and external-export tests
cover the implemented behavior without migrating historical paths.

## 2026-09-15 First Human UI Flow Readiness

### GAP-HUMAN-001 Bundled Example Human Acceptance Pending

Status: automated implementation complete; open pending revised manual
AC-HUMAN-001 signoff in Edge.

The normal project selector now lists `examples/Pillars.json` under Examples. Open
materializes or reuses the exact-name user copy; Duplicate requires confirmation
before JSON replacement and retains the paired user asset folder. Example
thumbnails resolve from valid user-copy assets. Offline domain, pipeline, and
Streamlit tests cover the revised contract.

Remaining impact: visual and interaction signoff in Edge has not been repeated for
the revised flow.

Human test observation, 2026-09-16: Edge required two separated clicks to activate
almost every tested radio button or checkbox. A controlled Chromium run accepted a
workflow radio change after one click. Remediation assigns stable explicit keys to
radio and checkbox widgets, removes the changing navigation `index`, and logs each
received widget change. Automated single-activation coverage and a renewed Edge
human test are required before this gap can close.

Next action: conduct the revised AC-HUMAN-001 procedure in
`docs/testing/ui_scene_coverage.md` using Edge.

Phase 6 observation, 2026-10-03: an isolated Chromium session opened the bundled
example, materialized and reopened its user copy, changed workflow screens with one
activation, displayed the background/coverage/stretch controls, surfaced a failed
download without losing the scene, and rejected export without a current render.
This closes the integrated technical browser check. It does not substitute for the
remaining user Edge signoff, so the gap stays open with that exact acceptance
boundary.

## 2026-09-19 Example Materialization Requirements Pass

### GAP-EXAMPLE-001 Example Catalog and User-Copy Workflow

Status: closed by implementation and automated verification on 2026-09-19.

The source catalog now contains JSON scene cards only, including the clean
`examples/Pillars.json` template. The former tutorial was preserved under `docs/`.
The previously tracked `artifacts/Pillars.json` was removed from source control.
For local human testing, that ignored user card and its `Pillars/` and
`Pillars.assets/` folders were explicitly migrated together to the configured
`artifacts/scenes/` user library; the separate legacy run remains ignored under
`artifacts/legacy-example-artifacts/`. Open, Duplicate, confirmation, JSON-only
replacement, identity preservation, user-copy thumbnail, and paired-folder
retention behavior are implemented and covered by tests.

Verification: focused suite 118 passed; complete offline suite 214 passed with the
single live archive test skipped by its opt-in guard.

### GAP-EXAMPLE-002 Stale Reprojection Replacement

Status: closed by implementation review and automated verification on 2026-09-19.

REQ-WCS-005 through REQ-WCS-007 permit stale reprojections to be replaced after a
canvas change only when the current JSON does not retain a successful render record
that references them. Explicit reuse of an unregistered scene workdir permits this
replacement, while `_reject_registered_output_overlap` protects referenced render
assets and downloaded source products remain unchanged.

Verification: `test_canvas_change_can_replace_unreferenced_reprojections` and
`test_scene_workdir_cannot_overwrite_registered_render_assets` cover the permission
and immutability boundary.

## 2026-09-20 Pillars Source-Coverage Investigation

### GAP-FITS-001 HST DRC Weight and Context Masks Are Not Applied

Status: closed by implementation and real-scene render verification on 2026-09-21.

The two prominent bands in the Pillars composite are already present in all three
selected HST/WFC3 UVIS `*_drc.fits` products. Their `WHT` extensions contain two
matching zero-weight bands, their `CTX` extensions report zero contributing input
images there, and their `SCI` extensions retain sparse bright residual pixels. The
Galaxy FITS loader currently consumes `SCI` and an optional `DQ` extension only;
these DRC products contain `SCI`, `WHT`, and `CTX` but no `DQ`, so the zero-coverage
pixels are treated as valid science samples and become conspicuous after RGB
composition.

Impact: the gap geometry originates in the archive products rather than Galaxy
reprojection, but Galaxy does not yet honor the archive products' available
coverage metadata when constructing a validity mask.

Resolution: REQ-FITS-001 through REQ-FITS-004 define native-unit and validity-mask
semantics. The loader now combines nonzero `DQ`, nonpositive or nonfinite `WHT`,
and zero `CTX` samples; reprojection excludes invalid pixels and records the mask
sources and valid coverage. Deterministic FITS and reprojection tests pass.

Verification: revision 5 rebuilt all six local source products in
`render-r5-0ca41ad81945`. Each HST plane records `WHT` and `CTX` as mask sources,
valid output coverage near 18 percent, and a nonzero RGB contribution. Inspection
of the generated thumbnail confirms that the two formerly prominent zero-weight
bands no longer contribute residual science pixels to the composite.

### GAP-NORM-001 Pillars Display-Normalization Adoption

Status: closed by scene-card revision and render verification on 2026-09-21.

REQ-NORM-001 through REQ-NORM-006 and the supporting schema, composition,
provenance, inventory, and warning behavior are implemented. Both the bundled
example and existing user copy now use 0.5/99.5-percentile normalization followed
by an asinh stretch with parameter 4.0 and unit gain. The bundled card is revision
4; the user card is revision 5 and retains its prior render history and FITS assets.

Verification: `render-r5-0ca41ad81945` completed from the six existing local FITS
files with no display warnings. All six planes record percentile black/white
points, positive valid coverage, and nonzero RGB contribution. The three HST
planes contribute about 48 percent of red, 44 percent of green, and 31 percent of
blue before final channel tone processing, confirming that they are no longer
suppressed by the differing native units.

### GAP-COMP-001 Cross-Instrument Coverage Edges Remain Visible

Status: closed for explicit truthful-support selection on 2026-09-30; the separate
full-union seamless-presentation request is tracked as GAP-COMP-002.

The normalized composite clearly reveals the smaller HST/WFC3 footprint over the
larger JWST/NIRCam mosaic. Pixels covered by different subsets of normalized planes
change brightness and color abruptly at footprint boundaries. This is distinct
from the closed zero-weight-band defect: invalid samples are now excluded, but the
RGB compositor does not feather coverage edges or compensate for a changing set of
contributors.

Impact: the result is scientifically traceable and proves that every selected
plane contributes, but it is not yet a seamless presentation composite.

Resolution: COVERAGE-001 and REQ-COV-001 through REQ-COV-008 independently select
output support and tone-statistics support. The accepted default retains all
2,356,011 union pixels in mixed Pillars while resolving one global channel transform
from the 428,810 pixels supported by every required plane. The transform is applied
unchanged outside the overlap: no contributor-count division, gain compensation,
or invented measurement is used. Optional common-only output and WCS-aware crop
remain available. Synthetic mask/crop/WCS tests and the reproducible real-scene
report are stored under `artifacts/phase4-coverage`.

### GAP-COMP-002 Seamless Full-Union Presentation Is Not Implemented

Status: open with durable Phase 4 disposition on 2026-09-30.

Union output intentionally retains physical changes caused by a changing set of
contributors, while common-overlap tone statistics prevent partial areas from
defining or receiving their own visual range. This does not produce a seamless
full-union mosaic. Feathering, overlap matching, same-band stacking, and any
contributor-count compensation require separate requirements and scientific
acceptance and are not authorized by Phase 4.

### GAP-EXAMPLE-003 Pillars JWST Pins Do Not Overlap the Canvas

Status: closed by selection remediation, source replacement, and render verification on 2026-09-20.

The three selected JWST/NIRCam detector-level I2D products have sky centers about
5.82 to 5.99 arcminutes from the Pillars scene center. The configured 5000-pixel
canvas at 0.08 arcseconds per pixel is only 6.67 arcminutes wide. All three stored
JWST reprojections therefore have zero footprint coverage, and the existing
composite is effectively HST-only.

Impact: the example suggests a six-filter HST/JWST composite, but only its three
HST planes currently contribute image data.

Resolution: the bundled example now pins the program-2739 Observation-1 Level-3
association mosaics for F090W, F200W, and F444W. The user copy stores all six
source FITS files under the identity-hashed scene-owned source layout. Product
selection now groups by authoritative parent observation, prefers combined
Level-3 images over detector components, and treats unknown exposure depth
explicitly. Pipeline execution rejects any selected plane with zero measured
reprojection footprint.

Verification: the corrected revision-4 scene rendered all six filters successfully
at 150 degrees in `render-r4-19f0904653aa`; the measured-coverage gate passed for
every selected plane. Focused selection, pipeline, and scene-card verification
reported 102 passed. Thirty exact obsolete detector FITS/reprojection/footprint
files were removed; mixed HST composites and diagnostic metadata were retained.

## 2026-09-22 Guided Candidate Selection Requirements

### GAP-GUIDANCE-001 Candidate normalization and guided selection

Status: closed by implementation and offline verification on 2026-09-22.

A Horsehead Nebula human flow returned 799 archive rows representing 435 unique
downloadable identities. The earlier `deepest_per_filter` proposal checked 37 rows
but only 25 unique identities across 25 filters; twelve checked rows repeated
identities. The flat editor also omitted selection scale, download consequences,
product-choice explanations, and stage guidance.

Resolution: authoritative identities are now consolidated before ranking,
persistence, and display. Conflicting metadata remains explicit. Candidate
manifests carry mode, scope, and custom state, are registered as scene-owned assets
before Apply, and restore without a new query. Refinement supplies Preview, Full
filter, and Custom modes; All, HST, and JWST scopes; unique product/filter/mission/
instrument and size summaries; grouped recommended products and alternatives;
concise explanations; clear/restore controls; explicit Apply; ordered next steps;
and technical diagnostics behind `Technical readiness details`.

Verification: `tests/test_selection_guidance.py` covers duplicate/conflicting rows,
all modes and scopes, deterministic custom selections, known and unknown sizes,
concise explanation limits, scene save/reopen before Apply, missing/corrupt assets,
grouped alternatives, and readiness disclosure. Sixty-two focused selection,
MAST, and UI tests passed. The complete offline suite reported 238 passed and one
opt-in live-archive test skipped. No intermediary Phase A through D gap remains.

## 2026-09-22 Render Launch State

### GAP-RENDER-STATE-001 Existing drafts rendered stale disk state

Status: closed by implementation and automated verification on 2026-09-22.

An existing saved draft could become render-ready in memory after applying selected
products and recommended defaults, but `Generate preview` saved only scenes without
an existing path. The background worker then reopened the older JSON from disk and
reported missing selection, plane, tone, and PSF fields even though the live UI had
validated the newer state.

Resolution: render launch now saves whenever the live scene differs from the saved
document, as well as for a new unsaved scene, before starting the file-backed worker.
A save failure prevents launch and retains the live scene for correction.

Verification: `test_render_launch_requires_save_when_live_scene_differs_from_disk`
covers new, unchanged saved, and changed saved scenes. The focused selection/MAST/UI
suite reported 62 passed; the complete offline suite reported 238 passed with one
opt-in live-archive test skipped.

### GAP-RENDER-STATE-002 Resolved target metadata rejected at render launch

Status: closed by implementation and automated verification on 2026-09-22.

A resolver-created scene card could validly contain `target.resolved_name`, but the
render bridge copied that display/provenance field into `TargetConfig`, whose
unknown-field policy rejected it before processing. Filename casing and scene-path
deduplication were not involved.

Resolution: the scene-to-processing bridge now uses an explicit allowlist of
`TargetConfig` fields. The frozen scene card retains `resolved_name`, while the
processing target receives only the typed query, coordinates, region, and supported
coordinate forms. Resolver drafts no longer duplicate the typed query into
`resolved_name`; a distinct resolver-supplied label is still retained.

Verification: the exact saved `horsehead-nebula-4c17a154.scene.json` now prepares
successfully. Focused pipeline/UI verification reported 51 passed. The complete
offline suite reported 240 passed with one opt-in live-archive test skipped. The
pytest cache directory remained unavailable under the junction-backed checkout,
producing two non-functional cache warnings.

## 2026-09-23 User Project Deletion Requirements

### GAP-DELETE-001 User-owned projects cannot be deleted

Status: closed by implementation and automated verification on 2026-09-24.

Saved scenes can currently be opened or duplicated, but the project selector has no
Delete action. REQ-LIB-020 through REQ-LIB-026 now define deletion only for
user-owned stored scenes, explicit scope confirmation, bundled-example protection,
recoverable card-and-asset-root handling, rollback on partial failure, active-job
guards, active-scene closure after success, and filesystem-derived library refresh.

Resolution: Saved scenes now provides an Open-style Delete action only for
user-owned cards. Confirmation identifies the exact card and canonical asset root.
The transaction moves both into a unique `.galaxy-trash` recovery directory,
writes a recovery manifest, rolls back partial moves, protects bundled examples,
blocks deletion during the active scene's render, closes a deleted active scene,
and refreshes from disk. Focused transaction and Streamlit tests pass.

## 2026-09-24 Selected FITS Footprint Framing Requirements

### GAP-FRAME-001 Initial canvas does not fit selected scans

Status: closed by implementation and automated verification on 2026-09-24.

The current new-scene canvas is derived from the target search region before exact
FITS footprints are inspected. A Horsehead Nebula scene using three selected JWST
products therefore rendered only a small portion of the available scan area.
The saved canvas is 120 by 120 pixels at 1 arcsecond per pixel, a 2 by 2 arcminute
field centered on the resolved target. Inspection of the three downloaded JWST
I2D celestial WCS footprints found their centers about 2.06 arcminutes from that
target and footprint diagonals of about 3.10 to 3.15 arcminutes, so the configured
target-centered canvas cannot enclose them.

REQ-REFINE-033 through REQ-REFINE-039 and REQ-WCS-009 through REQ-WCS-016 now
require an initial fitted canvas derived from all selected valid FITS footprints, a
manual `Fit selected scans` action, deterministic tight orientation, bounded
padding and preview raster size, preservation of accepted user frames, and measured
warnings for disconnected, sparse, widely separated, or excessively large unions.
The supporting algorithm and thresholds are defined in
`docs/viewport_framing_spec.md` and acceptance coverage in AC-FRAME-FIT.

Resolution: selected valid FITS support now drives a deterministic padded
minimum-area TAN canvas with containment verification and a 2048-pixel preview
cap. Refinement offers `Fit selected scans`, quantitative preview diagnostics,
warning choices, Apply, and Keep. Warning-free provisional frames are fitted and
persisted before first-render history is committed; accepted and manually edited
frames are not silently refitted. Offline WCS tests cover rotation, RA zero,
invalid support, extreme separation, preview capping, UI acceptance, and automatic
persistence. The real three-file Horsehead selection produced one component, no
warning, and a 2023 by 2048 fitted frame at 0.068156 arcsecond per pixel.

### GAP-FRAME-002 Fit preview shows a stale clipped render overlay

Status: closed by implementation and automated verification on 2026-09-24.

The numerical fit is correct, but Refinement continues to display the last
rendered `footprints.png`. For the Horsehead scene that asset was projected into
the former 120 by 120 target-region canvas, so it shows only a diagonal clipped
corner after `Fit selected scans`. The pending fit has no freshly generated visual
preview, which makes the fitted result appear unchanged.

Resolution: the fit result now retains the exact sky-boundary vertices used by the
geometry calculation. Refinement rasterizes every selected boundary in a distinct
color through the proposed output WCS and draws the proposed canvas border before
Apply. Stored render overlays are shown only when `matching_render` proves that the
render snapshot is current; otherwise the UI identifies the overlay as stale.
Geometry, Streamlit, stale-overlay, and real Horsehead visual checks pass.

## 2026-09-27 Presentation Feature Assessment

Review: [20-feature assessment and phased proposal](presentation_feature_assessment.md).
The review is complete; proposed features have not been accepted as requirements.
The existing cross-instrument coverage entry titled GAP-COMP-001 remains open.

### GAP-PSF-MASK-001 Invalid source values influence deconvolution neighbors

Status: closed by validity-aware Richardson-Lucy implementation and regression on
2026-09-28.

`build_deconvolved_plane_artifacts` passes source data to Richardson-Lucy without
the validity mask and reattaches the mask afterward. Convolution therefore permits
invalid values to influence valid neighbors. The review records a deterministic
masked-center perturbation diagnostic. Define mask-aware processing and add a
regression before extending empirical PSF or regularized deconvolution behavior.

Resolution: PSF-RL-001 is now normative through REQ-PSF-010 and REQ-PSF-012.
The active native branch supplies FITS validity to a sensitivity-normalized masked
RL update, fixes invalid latent samples to zero, and rejects valid negative samples
instead of clipping them. `test_masked_values_do_not_change_valid_richardson_lucy_output`
changes the masked center by six orders of magnitude and verifies invariant valid
output; the signed-input regression verifies the explicit failure policy.

Verification: PSF/reprojection tests reported 14 passed before the native-WCS
regression was added; PSF, reprojection, pipeline-mode, and scene-pipeline
integration then reported 45 passed. Subsequent package-contract integration and
the corrected explicit-native UI fixture leave the complete offline suite at
263 passed with one opt-in live test skipped.

### GAP-PSF-SCALE-001 Angular Gaussian width lacks pixel-scale conversion

Status: closed by native-sampling conversion and regression on 2026-09-28.

`_gaussian_kernel_from_fwhm` uses a value named in arcseconds directly on a pixel
grid. The caller does not supply native source pixel scale. Specify the conversion
and verify behavior across different input scales before relying on this path.

Resolution: PSF-GAUSS-001 is now normative through REQ-PSF-011. The active native
branch derives two celestial pixel scales from WCS, rejects degenerate or skewed
geometry, converts angular FWHM with the exact Gaussian relation, samples an
anisotropic pixel-space kernel when needed, and validates finite nonnegative odd
kernel dimensions. The array-only helper requires explicit pixel scales.

Verification: `test_gaussian_kernel_converts_angular_width_to_pixel_sampling`
covers two native scales and anisotropic sampling; integration results match the
GAP-PSF-MASK-001 evidence above.

### Phase 1 image-contract and stage-boundary closeout

Status: complete on 2026-09-28; no intermediary Phase 1 gap remains open.

FITS and aligned-plane packages now validate explicit validity, coverage, domain,
celestial WCS, WCS/shape grid identity, branch and lineage. Derived arithmetic,
normalization and RGB mixing use explicit typed stage results without modifying
caller arrays. The frozen Phase 0 recipe has a known-answer regression at
`rtol=atol=1e-6`. Focused Phase 1 integration reports 106 passed; the complete
offline suite reports 267 passed and one opt-in live archive test skipped.

Checkpoint identity/integrity, shared scene/direct rendering, encoding, background,
cross-instrument coverage and later tone work remain assigned to their existing
Phase 2-or-later entries; none is an untracked Phase 1 carryover.

### GAP-BG-001 Horsehead valid sky remains blue

Status: open investigation and requirements proposal, not a confirmed physical
calibration defect.

Both inspected Horsehead thumbnails, including `render-r7-normalized-tone`, show
blue valid sky. All three planes are JWST data in MJy/sr. The user's leading
hypothesis is a high black baseline in one filter. F187N supplies blue and has a
recorded 0.5th-percentile black point of 4.0305 MJy/sr, versus 0.5399 and 0.2060
for F212N and F250M. A constant additive offset alone cancels under percentile
normalization; compare sky residuals over common source-masked regions to determine
whether the quantile misses the sky pedestal or the baseline varies spatially.
Propose masked background estimation and explicit presentation black-reference
behavior without automatically suppressing real diffuse emission.

Phase 3 implementation status (2026-09-29): the bounded pedestal workflow and
`corrected_zero` presentation policy are implemented and automatically verified.
A reproducible candidate using one common 250 x 250-pixel source-poor region found
pedestals of 10.1112308502, 1.6341290474, and 0.2318623811 MJy/sr for F187N,
F212N, and F250M respectively. The candidate reduces much of the blue sky but also
produces strong green/yellow shifts in parts of the field. The exact region,
diagnostics, commands, and output locations are recorded in
[`phase3_background_evidence.md`](phase3_background_evidence.md).

Human assessment on 2026-09-29 found the candidate significantly better but could
not determine whether the selected background region is correct. Phase 3 is closed
because the complete workflow is usable and its presentation result is accepted.
This gap remains open for region validation and physical interpretation; no
physical-calibration conclusion is claimed, and later phases shall not silently
treat the region as ground truth.

### GAP-DUP-001 Asset-backed user-scene Duplicate could not be saved

Status: closed on 2026-09-29 before Phase 4 example preparation.

The Saved scenes Duplicate action created an unsaved draft that retained paths
owned by the source scene. Saving under the new scene identity then failed because
the new asset paths were not materialized. The Phase 4 Pillars source set is about
12.5 GB, so an unbounded in-memory or unconditional full byte copy is not an
acceptable repair. Close this gap only after Duplicate commits a new identity,
materializes verified immutable inputs at new scene-owned paths using hard links
with a streaming-copy fallback, drops generated history, survives deletion of
either path, and has focused UI/workflow regression coverage.

Resolution evidence: `duplicate_scene` now performs transactional input
materialization and `duplicate_library_scene` commits the new scene before opening
it. The focused scene-card/UI suite reports 115 passed. The complete offline suite
reports 293 passed and one opt-in live archive test skipped. A temporary duplicate
of the current Pillars scene resolved all 9 retained assets (12,496,116,942 logical
bytes) through hard links, reported zero dependency issues, retained no render or
export history, and was removed without affecting the original paths.

### GAP-APPLY-001 Reduced selection retained stale mappings and lost local pins

Status: closed on 2026-09-29 before Phase 4 example preparation.

Applying an HST-only selection to the duplicated mixed Pillars scene correctly
updated selected products and enabled filters, but retained the copied JWST mapping
rows. Render readiness then rejected F090W, F200W, and F444W as unknown filters.
The same Apply action rebuilt product records without their `cached_asset_id`
values, leaving the hard-linked HST files present but unreachable through the
selected-product execution path. Close this gap only when explicit Apply replaces
selection-dependent defaults for exactly the selected filters, preserves or safely
recovers matching local source references, retains the accepted canvas, enables
Render absent an independent problem, and covers the reduced mixed-to-HST case.

Resolution evidence: explicit Apply now replaces selection-dependent defaults and
recovers valid local source references by retained product identity, conventional
source asset identity, or a unique exact source filename. Replaying the affected
saved HST-only Pillars clone in memory produced mappings only for F502N, F657N,
and F673N, resolved all three selected hard-linked FITS paths, and returned zero
Render-readiness issues. The focused regression passes and the complete offline
suite reports 294 passed with one opt-in live archive test skipped.

### GAP-TITLE-001 Clone storage label and Saved-scenes inline rename

Status: requirements complete; implementation not started.

User-scene Duplicate currently derives its default filename from the generated
display title `<source-title> copy`, even though the new scene-ID prefix already
provides uniqueness. Saved scenes also render titles as noneditable headings, so a
display-title change requires another screen or manual JSON editing. REQ-LIB-027
through REQ-LIB-034 now require the clone display title to retain ` copy`, require
clone storage names to omit only that generated suffix, and define an accessible
in-place title editor with atomic persistence, cancellation, failure behavior,
operation guards, and identity/path/history preservation. No runtime code or saved
scene was changed in this requirements pass.

Phase 6 disposition: this is a separately requested lifecycle/UI enhancement, not
an intermediary image-processing gap. The user explicitly deferred its
implementation until after the two Phase 4 example scenes were prepared. It remains
requirements-complete and intentionally unimplemented; Phase 6 made no title or
clone-filename behavior change.

### GAP-TONE-001 Controlled stretching

Status: closed by Phase 5 implementation and verification on 2026-10-02.

The legacy output stage supports independent channel asinh/gamma curves but lacks
an explicit color-preserving shared-intensity mode, persisted proposal workflow,
and verified GHS. REQ-TONE-002 through REQ-TONE-013 and TONE-SHARED-001,
AUTOSTRETCH-001, and TONE-GHS-001 define the bounded closeout contract. This gap
is closed by the typed tone models, numerical implementation, Streamlit workflow,
schema and provenance integration, 321-pass offline suite, and retained A/B
evidence in `phase5_stretch_evidence.md`. GHS and auto-stretch remain explicit
choices; neither is a forced default. Integrated manual workflow retesting remains
assigned to Phase 6 rather than an open Phase 5 implementation gap.

### GAP-REPROJECT-BRIDGE-001 Small missing stellar cores enlarge during resampling

Status: pipeline, aligned persistence/checkpoints and saved UI switch implemented
and technically verified on 2026-10-08; open only for user full-scene presentation
acceptance. See final evidence in [the owning plan](reprojection_bridge_plan.md).

Native Pillars F090W contains six NaNs with zero WHT and no CON contributors at
DS9 X=3727..3729, Y=6026..6027. Strict adaptive resampling expands their effect to
a 4 by 4 invalid square stored as black. REQ-BRIDGE-001..021 specify default-on
bounded presentation estimation during reprojection and strict opt-out. See
`../reprojection_bridge_spec.md` and `reprojection_bridge_plan.md`. The current estimator/profile is defined by
[BRIDGE-MEDIAN-001](../reprojection_bridge_algorithm.md); native and integrated verification are recorded in the owning plan.

Historical bridge review update (2026-10-06; superseded by integration closeout): current code supports bounded development;
25 focused FITS/reprojection/plane/checkpoint tests pass. REQ-BRIDGE-001..021
now specify automatic original-copy preparation during source loading, saved
switch behavior, branch isolation and stale-checkpoint handling. Complete
`reprojection_bridge_plan.md` before Phase 7 P2 selection. BR-F01..05 remain
open development findings owned by that plan; no bridge implementation is claimed.

## Historical 2026-10-07 remaining-work register reconciliation

Bounded review: [remaining-work review](remaining_work_register_review.md).
GAP-TITLE-001 and GAP-REPROJECT-BRIDGE-001 remain unimplemented; the UI coverage
matrix now explicitly records REQ-LIB-027..034 as missing implementation/tests.

### Deferred P2 selection (not an accepted implementation gap)

[Processing upgrade plan](image_processing_upgrade_implementation_plan.md), Phase 7,
awaits explicit user selection after bridge closeout. The original 20 proposals in
[presentation feature assessment](presentation_feature_assessment.md) span
P0/P1/P2/P3 priorities; not all are P2 or accepted requirements. Selected methods
require bounded requirements/specifications and compliance subplans before code.
No algorithm is selected or implementation gap closed by this reconciliation.

### Historical bridge implementation start (2026-10-07)

GAP-REPROJECT-BRIDGE-001 remains open. Native boundary-median filling is implemented
in `src/galaxy/bridge.py` with 45 focused regressions and a verified real source
crop. Full-frame preparation took 1.17 seconds with 2.74 GiB peak resident memory;
committed-memory baseline and exact evidence remain in
[the owning plan](reprojection_bridge_plan.md). BR-F01..05 retain their remaining
integration/acceptance work. The production pipeline and UI do not yet call the
bridge; no default-On runtime behavior is claimed. P2 remains unselected.


### Bridge integration closeout (2026-10-08)

Pipeline and UI are implemented; BR-F01..04 are closed and BR-F05 technical
verification is complete. The remaining gate is user full-scene presentation
acceptance, owned by [the bridge plan](reprojection_bridge_plan.md). Default-On
Generate preview now exercises the bridge; no final TIFF is required to inspect
it. GAP-TITLE-001 remains unimplemented and P2 selection remains deferred.

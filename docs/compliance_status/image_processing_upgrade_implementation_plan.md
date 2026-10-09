# Image-processing infrastructure and presentation upgrade plan

Created: 2026-09-28. Status: PHASES 0 THROUGH 6 COMPLETE; Phase 7 awaits user selection.

## 1. Purpose and execution scope

Implement, in dependency order:

**P00 foundation + essential P0 fixes -> background/pedestal feature -> coverage and normalization policies -> improved stretching -> user-selected P2 algorithms.**

This is the next agent's execution guide. When instructed to implement this plan, proceed through Phases 0-6 without asking for repeated approval of ordinary implementation choices. The present request creates the plan only. Phase 7 algorithms require the user's explicit selection; do not infer that selection from priorities or implement speculative P2 infrastructure. Complete Phase 6 closeout before waiting for P2 selection. If P2 choices arrive earlier, record them but preserve prerequisite gates.

The plan defines a bounded initial feature set. Detailed atomic requirements and method specifications must be written into the normative documents before the associated code is changed. Resolve routine design details within this scope, document them and test them. Ask only for a genuinely missing user decision that changes scope or output interpretation; continue independent authorized work while waiting.

### Read first, in this order

1. Root `AGENTS.md` and any applicable nested instructions.
2. `docs/design_requirements.md` (source of truth), especially scope, FITS validity, normalization, PSF, WCS, render history and output requirements.
3. `docs/compliance_status/known_gaps.md`.
4. `docs/compliance_status/current_image_processing_architecture.md` (observed 2026-09-27 baseline).
5. `docs/compliance_status/presentation_feature_assessment.md` (all 20 proposals and limitations).
6. `docs/compliance_status/p00_processing_infrastructure_proposal.md` (foundation rationale and P00-01..13 proposal IDs).
7. `docs/artifact_storage_spec.md`, `docs/scene_card_schema.md`, `docs/scene_card.schema.json`, relevant `docs/testing/` matrices, and `docs/user_flows.md`.

Reinspect actual code; these documents are a baseline, not proof that the checkout remains unchanged. This handoff supersedes the earlier proposal only for execution order and the bounded scopes specified here. Do not silently override conflicting normative requirements: reconcile their text, examples and tests as part of the requirements work for the phase.

## 2. Operating rules

- Work in `C:\Data\dev\galaxy`; use `.venv\Scripts\python.exe` and pytest. Record the initial Git status. The checkout contains substantial user-owned uncommitted work; preserve it.
- Use normal project Python tooling and reusable Python scripts for diagnostics when needed. Do not introduce PowerShell helper scripts into this Python project.
- The checkout is junction-backed. If an editing tool rejects the path, do not repeatedly retry it. Stage with `apply_patch` in an authorized writable directory, copy the exact validated target through a junction-compatible mechanism, request tool escalation if necessary, and inspect the resulting diff. Re-read destination files before copying back to avoid replacing concurrent changes.
- Do not modify original FITS, overwrite retained renders, reset the worktree, migrate historical asset directories, or change existing user recipes merely to test a feature. Use new isolated scene copies and output directories. Do not use `.codex` for runtime assets.
- No plugin registry, arbitrary user-defined execution graph, distributed processing, general cache eviction system, or persistent output for every mathematical substep.
- Preserve the existing native PSF/original branch distinction, background-worker cancellation, atomic history commit, concurrent-edit safeguards and current/stale preview behavior.
- Keep disabled new features numerically compatible with legacy recipes except explicitly documented correctness fixes. Do not change old default normalization or silently remove their two-stage stretch.
- Never treat missing coverage as a measured zero, fractional coverage as inverse variance, or filter labels alone as universal physical band identity.
- Keep documentation and implementation truthful: a planned test is not coverage, automated UI tests are not human signoff, and a visually pleasing result is not proof of physical background removal.

## 3. Progress and traceability records

Maintain phase state in this document: `not started`, `in progress`, `automated complete / human check pending`, or `complete`. Add dated evidence, test commands/results and remaining work after each phase.

Create:

- `docs/image_processing_architecture.md`: the central referenceable image-processing architecture and mathematical specification described in Phase 0A below. Requirements reference stable sections/algorithm IDs in this document.
- `docs/processing_checkpoint_spec.md`: checkpoint format, identities, compatibility and legacy import.
- `docs/testing/processing_upgrade_coverage.md`: requirement -> implementation -> test -> verification state.

Keep image contracts, mask semantics, stage order and algorithm mathematics in the central architecture document rather than creating duplicate `processing_stage_spec.md` and `presentation_processing_spec.md` documents. If those documents already exist when work resumes, consolidate or reference them with one explicit owner for each contract; do not discard existing content silently. Keep the architecture tight: concise shared conventions followed by method-specific sections, not an implementation diary. Put generated review evidence and remediation logs under `docs/compliance_status/`, and fixture/render artifacts under `artifacts/`. Amend existing storage/schema/user-flow specifications rather than creating a competing contract.

For each phase: requirements/specification -> code -> regression/acceptance tests -> validation -> gap dispositions -> coverage matrix. Assign globally unique requirement IDs after checking the registry. P00-01..13 are proposal IDs to trace, not automatically existing normative IDs.

### Known issues to carry forward

| Existing finding | Planned owner | Closure evidence |
| --- | --- | --- |
| GAP-PSF-MASK-001 invalid samples affect RL neighbors | Phase 1 | Masked-value perturbation does not change valid outputs |
| GAP-PSF-SCALE-001 angular Gaussian width used as pixels | Phase 1 | Correct sampling at multiple native pixel scales |
| Cross-instrument GAP-COMP-001 | Phase 4 | Explicit incomplete-color/common-support policy, synthetic and real-scene evidence |
| GAP-BG-001 blue Horsehead sky | Phase 3, revisited 4-6 | Measured common-region diagnostics and user-reviewable presentation result; physical cause may remain qualified |
| GAP-STORAGE-001 canonical storage implementation | Phase 2, bounded scope | New checkpoint/diagnostic outputs comply; retain residual legacy producer work explicitly if outside scope |
| Direct preview drops footprints | Phases 1-2 | Same numerical core and supported-pixel behavior |
| Derived arithmetic drops validity/WCS/units | Phase 1 | Operand-support and metadata tests |
| PNG-based TIFF export / wrong preview branch | Phase 2 | High-depth values and selected branch preserved through UI export |

The register currently reuses GAP-COMP-001 for an older closed directory issue. Avoid creating more duplicates. Disambiguate by title; if IDs are repaired, update references with a documented alias rather than losing historical traceability. Reassess broad existing coverage claims such as REQ-FITS-003 being fully covered when this review found uncovered paths.

## 4. Phase 0 — establish a reproducible baseline

Status: complete on 2026-09-28. No runtime behavior changed.

Evidence: [`image_processing_upgrade_baseline.md`](image_processing_upgrade_baseline.md)
records the inspected routes, environment, real-scene hashes, deterministic fixture
inventory, compatibility boundary, and initial traceability. The complete offline
suite reported 250 passed, 1 pre-existing failure, and 1 opt-in live test skipped.
The failure is identified in the baseline and was not bypassed.

1. Read the documents above and inspect the active routes in `fitsio.py`, `psf.py`, `reprojection.py`, `planes.py`, `mapping.py`, `tone.py`, `pipeline.py`, `scene_execution.py`, `scene_pipeline.py`, `scene_models.py`, `scene_card.py`, `scene_readiness.py`, `scene_workflow.py`, `ui.py`, `export.py` and `provenance.py`.
2. Record current stage order, dataclass fields, scene/schema revision policy, dependency versions and all consumers of image arrays/footprints. Use the existing architecture baseline; update only verified differences.
3. Run baseline offline tests with the local virtual environment; inspect opt-in network-test rules first. Classify existing failures separately from new failures. Do not invent a passing baseline from older counts.
4. Build small deterministic fixtures: different numerical units/scales, masked bright outlier, negative finite samples, constant/empty fields, partial RGB overlap, internal holes, mismatched WCS, ratio singularity, and a 16-bit gradient with more than 256 levels.
5. Select existing Horsehead and mixed HST/JWST Pillars artifacts by scene references and verify their files. Prior Horsehead evidence: `horsehead-nebula-3426555b.scene.json` and `render-r7-normalized-tone`. Preserve originals and use copied recipes for comparisons. Do not redownload data when verified local sources suffice.
6. Freeze a legacy input recipe and record expected numerical outputs/tolerances. Record source hashes and material test environment details. Synthetic fixtures are the automated correctness oracle; real images provide diagnostic and human acceptance evidence.

Exit: baseline report and initial traceability/gap list exist; expected legacy behavior and intended corrections are distinguishable. No algorithm behavior has changed.

### Phase 0A — reference-backed image-processing architecture (mandatory P00 gate)

Status: complete on 2026-09-28. Execute after baseline inspection and before Phase 1 implementation.

Evidence: [`docs/image_processing_architecture.md`](../image_processing_architecture.md)
defines the Phase 1 image/mask/stage contracts, corrected PSF sampling and
validity-aware RL method, derived arithmetic, legacy extraction boundaries,
encoding identity, persistence boundaries, references, and independent
known-answer cases. Phase 3-5 methods are explicitly inventory items with
phase-owned finalization gates; unselected P2 methods remain deferred. The source
of truth now links the architecture and initial coverage matrix.

Create `docs/image_processing_architecture.md`. The user explicitly requested this architecture as the bridge between capability requirements and implementation. The earlier current/proposed flowcharts remain descriptive baseline/planning artifacts; neither substitutes for the mathematical specification.

**Document authority and traceability:** `docs/design_requirements.md` states required observable capabilities, constraints and acceptance. The architecture is its supporting technical specification: it defines precise processing semantics and selected algorithms and is incorporated by explicit references. Requirements remain the source of truth. A design choice in the architecture must trace to a requirement or be labeled proposed; the architecture must not silently authorize new features. Use stable section/algorithm IDs and document revisions so requirements and tests can cite exact definitions. Extend the coverage matrix to requirement -> architecture section/method -> implementation -> independent verification.

**Required contents:**

1. Scope, document authority, notation and a compact stage/data-flow diagram, including branch boundaries and reusable checkpoints. Distinguish existing behavior, specified target behavior and deferred proposals.
2. Shared image contracts: floating values; native/calibrated versus display domains; units; WCS and sampling; array ownership; source/branch identity; validity; fractional coverage; and separately defined sample-selection/source-exclusion regions. Explain that coverage is not statistical weight and a normalization is not physical calibration.
3. Missing-data semantics: zero is a legitimate measured value; NaN/nonfinite samples are unusable numerical values, not black measurements. Define how explicit validity masks and NaN interact at every boundary, which representation is authoritative, and how finite-but-invalid samples are handled. Preserve valid negative values. Specify ingestion, reductions/percentiles, arithmetic, convolution, reprojection, FITS persistence and display conversion. If a storage/library boundary uses zero-filled arrays plus masks, require paired masks and prohibit consumers from interpreting fill values as observations. Decide representation explicitly rather than demanding NaN everywhere or treating NaN handling alone as complete validity propagation.
4. A compact method specification for each current operation being retained or corrected, and each selected Phase 3-5 method. Include background estimation, normalization references, coverage policy, RGB mapping/tone, sampling/reprojection and PSF treatment as applicable. Explain how the chosen baseline reference survives successive stages.
5. Shared numerical/failure conventions: empty or constant samples, zero denominators, nonfinite values, insufficient support, boundaries/padding, clipping/gamut, signed inputs, precision and reproducibility tolerances. Method sections override shared conventions only explicitly.
6. References and adaptation record, compatibility/versioning rules, and links to checkpoint/storage/schema contracts rather than duplicating their full definitions.

**Every algorithm section must contain:** purpose and stable ID; exact named variant; authoritative paper/author documentation with bibliographic details, DOI or durable URL and relevant equation/section identifiers when available; input/output domains and units; assumptions; equations with all symbols defined; parameter meanings/defaults/ranges; processing order; validity/support and boundary behavior; stopping/failure conditions; diagnostics/provenance; numerical tolerances; and reference examples or synthetic known-answer cases. Identify Galaxy-specific adaptations and presentation policies as such. Do not describe a heuristic regularization blend as a published regularization objective without evidence.

**Research and independent implementation workflow:** use other applications to discover capabilities; obtain primary mathematical references; write Galaxy-specific requirements and mathematical specifications; then implement and verify from those specifications. A bibliography assembled from search snippets is insufficient: read the cited equations/method sections and verify they support the selected variant. Do not transcribe another application's function structure into pseudocode and call it an independent design. Record any deliberately reused code and its license separately. Public algorithms still require precise variant selection; do not invent citations or assume a named method has only one implementation.

**Bounded sequencing:** complete the shared architecture, planned stage interfaces and precise specifications needed for P00/essential P0 before Phase 1 coding. Establish the Phase 3-5 method inventory and research references during P00; finalize each later method's mathematics and acceptance examples before its phase begins coding. Unresolved variants must be explicitly marked and cannot pass their implementation gate. User-unselected P2 methods get insertion points and prerequisite notes only; do not prematurely choose their algorithms or expand scope.

**Exit:** the architecture exists, is linked from the requirements and this plan, and resolves the data/mask/stage contracts needed for Phase 1. Its P00 methods have verifiable references/specifications and known-answer test definitions. A reader can implement these methods without consulting a competitor's source code. Remaining Phase 3-5 research tasks have phase ownership; P2 remains pending selection. Creating headings or copying the existing flowchart does not satisfy this gate.

## 5. Phase 1 — image contracts, stage boundaries and essential P0 fixes

Status: complete on 2026-09-28. Phase 0 and the Phase 0A architecture gate are complete.

Requirements evidence: REQ-IMG-001 through REQ-IMG-006,
REQ-DERIVED-001 through REQ-DERIVED-002, and REQ-PSF-010 through REQ-PSF-012
promote the applicable foundation and essential P0 behavior and reference the
stable architecture definitions. Runtime migration and acceptance tests remain.

Implementation evidence: the Phase 1 foundation now implements PSF-RL-001 and
PSF-GAUSS-001 in `src/galaxy/psf.py`, closing GAP-PSF-MASK-001 and
GAP-PSF-SCALE-001. `FITSPlane` and `ReprojectedPlane` now carry required validity,
coverage, domain, branch, lineage, celestial WCS and a verified WCS/shape grid
identity. Derived linear combinations and ratios return full packages, propagate
support and identity, reject wrong grids/branches/units and singular denominators,
and preserve their inputs. FITS export/import restores WCS, composition consumes
packages directly, and direct aligned-FITS preview now supplies footprints to the
shared composition path. Normalization returns a typed unitless `display_plane`
package, and RGB mixing accepts only same-grid display packages and returns typed
channel/support/signal results. The frozen Phase 0 legacy recipe passes at the
documented `rtol=atol=1e-6`. Focused Phase 1 integration reported 106 passed. The
complete offline suite reported 267 passed and one opt-in live test skipped.

Phase 1 exit is satisfied. No background, GHS, stacking, checkpoint, or other
later-phase algorithm was introduced during Phase 1.

### Requirements and implementation

- Implement against the referenced definitions in `docs/image_processing_architecture.md`; resolve mathematical/support-policy ambiguities there before coding and cite architecture IDs in verification records.
- Promote applicable P00-01..05 and compatibility requirements into normative requirements. Define a canonical validity convention; adapters may invert existing invalid masks.
- Evolve existing dataclasses to carry values, required validity, coverage, WCS/grid identity, unit/domain, branch and parent/source identity together. Preserve unknown metadata explicitly. Units distinguish native/calibrated linear data, display-normalized planes and RGB; do not imply normalization performs physical calibration.
- Enforce shape, finite usable samples and geometry invariants. Operations return new results without mutating input values/masks. Use ownership/read-only conventions to avoid indiscriminate full-array copies.
- Separate derived-plane computation, plane normalization, RGB mixing and tone into typed functions. Preserve the old order and arithmetic when new modes are disabled.
- Define operation-specific validity: weighted arithmetic requires its contributing operands; ratios require supported numerator/denominator and a specified near-zero denominator policy. Missing support must not become valid through epsilon addition. Exclude mathematically zero-weight operands appropriately.
- Preserve signed samples until an explicitly documented algorithm/display boundary. Do not use global clipping as an infrastructure fix.
- Repair PSF mask leakage. Specify a mask-aware RL update and support/boundary rule, or explicitly reject unsupported cases as an interim state. Rejection is not final completion of supported masked PSF processing; leave the gap open until the implemented method passes its gate. Do not introduce P2 deringing or a new regularization objective here.
- Convert angular kernel width using the native celestial pixel geometry. Define treatment of unequal pixel scales/rotation; either construct the appropriate pixel-space kernel or reject unsupported geometry explicitly. Validate supplied kernel finiteness, normalization and sampling compatibility.
- Define the signed-input policy for RL and test it; do not silently recast negatives as valid Poisson observations. Background correction introduced in Phase 3 occurs after the existing PSF/reprojection branch, so it must not silently feed signed residuals into RL.

Primary code: FITS/plane dataclasses and adapters, `mapping.py`, `tone.py`, `psf.py`, `reprojection.py`, call sites in `pipeline.py` and UI.

### Acceptance

- Replacing values underneath an invalid mask with extreme values leaves all valid results invariant within stated numerical tolerance, including spatial PSF operations.
- Derived sums/ratios preserve correct support and coordinate identity; wrong grids and singular inputs fail or mask exactly as specified.
- Input arrays and masks remain unchanged; FITS/WCS round trips preserve pixel-to-sky mapping.
- Same physical Gaussian width on two source scales yields the expected different pixel widths.
- Legacy unaffected paths match the Phase 0 baseline; intended bug-fix differences are enumerated rather than hidden in updated goldens.

Exit: current processing uses the contracts; mask fixes and PSF sampling behavior are verified. No background/GHS/stacking algorithm is added.

## 6. Phase 2 — checkpoints, shared rendering and output integrity

Status: complete on 2026-09-28. Phase 1 completed on 2026-09-28.

Requirements/specification evidence: REQ-OUT-005 through REQ-OUT-007,
REQ-CHK-001 through REQ-CHK-008, REQ-RENDER-010 and REQ-PROV-010 are normative;
`docs/processing_checkpoint_spec.md` defines their checkpoint, reuse, stage-record,
shared-rendering and output-role behavior.

Implementation evidence: `src/galaxy/checkpoints.py` provides strict versioned
manifests, canonical producer keys, separate FITS integrity checks and atomic
manifest publication. `src/galaxy/artifact_paths.py` places new branch artifacts
under `original/` or `deconvolved/` and resolves legacy flat runs without moving
them. FITS checkpoints persist validity, WCS, domain, branch and lineage.
`src/galaxy/rendering.py` is shared by pipeline and direct preview. Scene records
register checkpoint and high-depth roles; export requires an explicit branch and
copies the matching uint16 TIFF rather than transcoding the PNG. Provenance now
contains complete aligned-checkpoint stage records.

Acceptance evidence: checkpoint tests cover downstream reuse, upstream source,
canvas, validity-version, PSF-kernel and branch invalidation; missing/corrupt and
self-inconsistent manifests; renamed pairs; grid/plane mismatch; and the legacy
inspection boundary. Rendering tests cover partial-support parity. Scene/UI tests
cover old-card compatibility, branch separation, concurrent edits, cancellation,
explicit export roles and more than 256 uint16 levels. Canonical layout tests cover
bounded branch paths, canonical preference and legacy preservation. The focused
Phase 2 suite reported 73 passed before final acceptance additions. The complete
offline suite reported 282 passed and one opt-in live test skipped.

Phase 2 exit is satisfied. No background correction, coverage-policy, GHS,
stacking or user-selected P2 algorithm was introduced. GAP-STORAGE-001 is closed
for the bounded Phase 2 branch-output scope; GAP-STORAGE-002 assigned the broader
input/cache placement reconciliation to final closeout and is closed in Phase 6.

### Requirements and implementation

- Promote P00-06..13. Define checkpoint manifests containing format version, stage/domain/branch, parent and source content identities, grid, resolved upstream settings, mask/kernel identities, producer version and output hashes.
- Use deterministic canonical serialization for compatibility keys. Exclude timestamps/path relocation from numerical identity; include all upstream dependencies. Use output checksums separately for integrity. Specify algorithm implementation versioning instead of relying on the hardcoded application version string.
- Preserve WCS through load/re-export. Reuse checkpoints only after compatibility and integrity validation. Changing tone must permit aligned reuse; changing a source, canvas, upstream mask/kernel or native correction must reject/rebuild affected outputs.
- Make execution-mode behavior explicit: strict compose-only with an incompatible/missing checkpoint reports what is needed rather than silently recomputing an unknown path. Full rendering may rebuild in a new run directory. Reconcile this behavior with CLI requirements/tests.
- Legacy FITS stacks remain inspectable via an explicit adapter with disclosed missing metadata. Do not invent all-valid support for certified reuse. Where support truly cannot be recovered, require explicit import assumptions and record them; such imports are not equivalent to verified original checkpoints.
- Centralize artifact path/role registration consistent with the storage specification. Add specified locations/kinds for checkpoint manifests and later background/region diagnostics. Preserve old files and references; do not require wholesale historical migration.
- Route scene and direct-stack rendering through the same numerical core. Explicit presets may differ, but masks must not disappear and equal settings must give equal results.
- Keep settings synchronized across scene/processing models, JSON schema, translation, readiness, `effective_inputs`, snapshots, provenance and UI. Add only concrete feature sections as they are implemented; do not add arbitrary processor dictionaries.
- Select export artifacts by branch and role. UI TIFF export uses the matching 16-bit TIFF, not an 8-bit preview; selected branch is explicit. Missing high-depth output causes an actionable error, not disguised precision loss.
- Preserve cancellation and optimistic scene-history commit protections. Checkpoints/diagnostics must not be published as successful scene outputs after failure or cancellation.

### Acceptance

Test upstream/downstream invalidation, corrupt/missing manifests, renamed files, incompatible grids, old scene loading, branch separation, scene/direct-preview parity, stale detection after every new setting, concurrent edits and cancellation. Verify exported TIFF has uint16 data with more than 256 preserved levels and uses the selected branch.

Exit: P00 infrastructure is ready for a real correction stage. P00 is provisionally implemented; Phase 3 proves practical use. Update architecture and traceability.

## 7. Phase 3 — background diagnosis and masked pedestal feature

Status: complete on 2026-09-29. Automated implementation and verification pass;
human assessment found the Horsehead candidate significantly better. The selected
region's physical interpretation remains qualified under GAP-BG-001.

### Bounded feature scope

Implement `off` and `pedestal`, with persisted background inclusion regions and optional exclusion regions. Use a minimal usable region workflow (for example, bounded rectangular regions entered/adjusted with a visible overlay); a freehand image editor is not required. Store sky-coordinate regions with a defined geometry and rasterization rule so they survive canvas changes. Provide an explicit unsupported/insufficient-samples state.

Apply the correction to aligned **linear** samples before derived arithmetic/display normalization, independently per branch. Record stage placement. Retain the original source and pre-correction aligned checkpoint. Do not implement polynomial modeling, linked gradients or detector debanding in this phase.

### Essential mathematical requirement: subtraction must not cancel itself

Subtracting a constant pedestal and then recomputing both percentiles over the same pixels produces the same normalized values:

`((x - b) - (q_low - b)) / ((q_high - b) - (q_low - b)) = (x - q_low) / (q_high - q_low)`.

Therefore do not claim the blue sky is fixed merely because a background-subtraction function ran. This phase must include a named **background-referenced black policy** that uses the corrected sky zero (or explicitly configured offset in stated units) instead of immediately re-estimating an independent low percentile. Define how downstream channel tone retains that reference; otherwise its own black subtraction can undo the intended policy. Preserve legacy percentile behavior as a separate mode. Phase 4 extends this minimal reference policy rather than discovering this issue later.

### Requirements and implementation

1. Define source-exclusion masks separately from observation validity and coverage. For cross-filter comparison use the same sky region and report actual common valid samples, not different unreported sampling sets.
2. Specify a deterministic robust estimator, clipping parameters, minimum sample count/fraction and insufficient-sample behavior. A source-masked median is a reasonable bounded starting method; finalize exact rules in the specification before coding.
3. Report per-filter sample count, median, robust spread, selected black reference, and residual after normalization. Label spread as a diagnostic, not automatically physical detector noise.
4. Subtract the estimated constant only from valid samples; preserve signed residuals and unchanged coverage/WCS. Save fitted baseline, region masks/identities, estimator/resolved parameters and residual diagnostics in provenance. Persist model artifacts only where meaningful; a constant can be represented compactly plus a viewable diagnostic.
5. Provide Preview/Apply/disable controls, region overlay, before/after inspection and a visible warning for poor sampling. Apply persists parameters and makes prior renders stale. Auto-estimates are explicit proposals, not silently changing values every redraw.
6. Verify save/reopen, canonical render and compose-only reuse. Corrected results must depend on region/estimator identity, while unchanged pre-correction aligned samples remain reusable.

### Acceptance and Horsehead investigation

- Synthetic known pedestal: estimation error <= 0.1 input-noise sigma for the specified well-conditioned fixture; preserve a protected diffuse source's integrated signal within 1% in linear corrected space. State fixture seed, distribution and sample count.
- Padded/masked/outlier changes do not alter estimates; too few samples fails visibly; off mode preserves prior output.
- Include an end-to-end regression proving the background-referenced policy changes the rendered background as intended rather than algebraically canceling subtraction. No-coverage pixels stay zero and faint injected signal survives.
- Inspect the same source-masked sky regions across Horsehead F187N/F212N/F250M; record before/after data and corrected output. The user's high blue-filter black-baseline explanation is the leading hypothesis, not established physics. A high raw baseline alone is not proof.
- Request user assessment of the candidate sky regions/result when needed for real-scene interpretation. Synthetic acceptance and independent work continue; label human acceptance pending rather than guessing that all diffuse blue emission should be removed.

Exit: complete human-usable pedestal workflow through save/reopen/export, with honest evidence about Horsehead. Foundation is proven by a real stage. Keep GAP-BG-001 open if the symptom or interpretation remains unresolved.

### Implementation evidence

The `off` and `pedestal` modes, ICRS inclusion/exclusion rectangles, deterministic
sigma-clipped estimator, branch-specific resolved values, `corrected_zero` black
policy, Preview/Apply/disable UI, branch diagnostics, provenance, checkpoint reuse,
save/reopen, and canonical render integration are implemented. Automated coverage
is recorded in the processing-upgrade coverage matrix. The reproducible Horsehead
candidate and measured common-region diagnostics are recorded in
[`phase3_background_evidence.md`](phase3_background_evidence.md).

Final offline validation on 2026-09-29 reports 290 passed and one opt-in live
archive test skipped.

The candidate materially changes the blue-filter baseline but also shifts portions
of the nebula and sky toward green/yellow. Human assessment on 2026-09-29 found the
candidate significantly better but could not determine whether the selected region
is physically correct. Phase 3 is closed on presentation acceptance and complete
workflow evidence; GAP-BG-001 remains open because the region interpretation and
physical cause are not established.

## 8. Phase 4 — coverage and stable normalization policies

Status: complete on 2026-10-02. Automated implementation, real-scene evidence, and
the union-output/common-overlap-tone policy were accepted. Title-editing
requirements are explicitly outside this phase and were not implemented.

### Initial policy scope

Implement two explicit presentation policies: legacy available-contributor behavior, and **common required-band support**. Keep observation validity unchanged. Determine required bands from nonzero enabled mappings with stable identities, including derived dependencies. Do not divide unlike bands by contributor count or fabricate missing channels.

Common support is an output-support policy, not proof that every pixel in its bounding rectangle is valid. Provide optional bounding crop with visible area-loss preview; retain holes as unsupported. Define empty/disconnected intersections, padding and chosen-component behavior without silently selecting a component. Cropping must update WCS correctly and never relabel absent data as observed.

This bounded policy can remove incomplete-color areas by excluding them; it does not promise a seamless full-union mosaic. Feathering, cross-band overlap matching and same-band stacking remain future scoped decisions. Close the existing coverage gap only to the extent its documented acceptance is satisfied; carry any remaining full-union seamless-presentation request explicitly.

### Normalization scope

Retain legacy per-plane percentiles. Add persisted fixed numerical bounds and reference-region statistics using Phase 3 regions. A named reference records units/domain, coordinates, required coverage, resolved values and source/branch identity. Specify locked values versus explicit recomputation; avoid crop-dependent silent re-estimation. Do not automatically histogram-match physically different filters.

Expose policy choice, excluded area/coverage, normalization references and clipping fractions in the UI. Support before/after, Apply, save/reopen and consistent branch behavior. Background-referenced tone must remain distinguishable from independent channel percentile stretching.

### Acceptance

- Synthetic unequal filter footprints, a missing RGB band, holes and disconnected supports produce exactly specified masks/crops; no measured value is synthesized.
- Padding and view changes do not change locked normalization values; explicit recomputation is recorded and invalidates only the appropriate downstream stages.
- Test WCS after crop, region persistence, empty support, constant fields and all relevant legacy modes.
- Compare Pillars HST/JWST and Horsehead in legacy/common-support modes. Show the support/area tradeoff rather than hiding it with gain adjustments.

Exit: users can choose truthful support and normalization behavior; coverage gap dispositions and UI/test matrices reflect the actual delivered policy.

Implementation evidence: the complete offline suite reports 306 passed and one
opt-in live archive test skipped. Reproducible candidates and metrics for mixed
Pillars, HST-only Pillars, JWST-only Pillars, and Horsehead are recorded in
[`phase4_coverage_evidence.md`](phase4_coverage_evidence.md). GAP-COMP-001 is closed
for explicit support selection; GAP-COMP-002 retains the out-of-scope seamless-
union request. The accepted recommended behavior retains the complete union,
resolves brightness statistics from common overlap, and does not compensate pixels
covered by fewer planes. Phase 4 is closed; integrated manual UI retesting remains
part of Phase 6 rather than a Phase 4 implementation gap and was completed in the
isolated technical browser exercise.

## 9. Phase 5 — controlled stretching

Status: complete on 2026-10-02. Depends on Phase 4.

Implement in three substeps; retain old modes and settings. Do not globally replace legacy two-stage processing.

### 5A: shared-intensity color-preserving tone

Define an explicit alternative to independent per-channel tone. Specify the intensity definition, signed/zero handling, gamut behavior and support policy. For supported positive RGB and positive intensity L, apply a common multiplier `T(L)/L`. Preserve ratios before gamut handling; do not claim clipping also preserves them. Offer a deliberate single-main-stretch preset with linear per-plane normalization, without silently modifying old recipes.

Test zero/near-zero intensity, signed corrected samples, saturation, partial coverage and bright out-of-gamut pixels. Before clipping, positive supported channel-ratio relative error should be <= 1e-5 on the specified float fixture.

### 5B: deterministic auto-stretch proposal

Use the persisted background/reference samples to estimate parameters for a selected tone method. Define exact estimator, target placement and bounds. Reject empty/degenerate/object-dominated samples instead of assuming whole-frame MAD is sky noise. Show suggested values, sample confidence and clipping estimates; apply only through explicit selection. Persist requested algorithm and resolved numbers, with a Recompute action. Save/reopen must reproduce the same result without re-estimation.

### 5C: GHS

Add GHS as an optional method after specifying authoritative equations, parameter domains, limiting cases, endpoints and numerical tolerances. Consult primary documentation at implementation time; review licensing if reusing code. Do not invent a curve and label it GHS. Include linear/asinh/gamma compatibility and the common-intensity/per-channel application distinction. Do not add spline curves, masked local stretch or denoising here.

### Acceptance

Monotonicity, finite output, limiting/identity cases and fixed reference examples must pass. Tests must catch automatic parameter drift and unintended extra stretching. On agreed fixtures compare faint structure, background residual/spread, highlight clipping and RGB ratios. Generate real-scene A/B renders using unchanged source products and reproducible settings, retaining all earlier history.

Exit: human-usable stretch controls and previews, saved settings/provenance, complete tests and updated architecture. GHS is an available choice, not an unverified universal improvement or a forced new default.

Completion evidence: REQ-TONE-002 through REQ-TONE-013 and the three architecture
methods are implemented. Legacy omitted-field behavior remains independent
per-channel tone. Shared-intensity, clip/rescale, explicit single-main-stretch,
deterministic proposal Preview/Recompute/Apply, forward GHS, persistence and
provenance are covered by the 321-pass offline suite. Reproducible A/B candidates
for mixed/HST/JWST Pillars and Horsehead are retained under
`artifacts/phase5-stretch`; no scene card was modified. The evaluated cards do not
persist background regions, so their auto-proposal attempts correctly fail rather
than estimating from an unauthorized whole-frame sample. See
`phase5_stretch_evidence.md`. Phase 6 completed the integrated technical browser
retest; final user presentation acceptance remains separate.

## 10. Phase 6 — integrated closeout and handoff to P2 selection

Status: complete on 2026-10-03. Phases 0-5 complete.

Evidence: [`image_processing_upgrade_phase6_closeout.md`](image_processing_upgrade_phase6_closeout.md)
records the 322-pass offline suite, isolated integrated browser exercise, failure-
path coverage, uint16 real-output checks, runtime/working-set observation, complete
gap dispositions, documentation reconciliation, and the explicit P2 handoff. The
technical browser gate is complete; final user presentation acceptance and the
historical Edge-specific AC-HUMAN-001 event remain truthfully pending.

1. Run the complete offline pytest suite in `.venv`, investigate regressions, and record exact commands/counts. Keep live archive tests opt-in and do not claim them tested without running them.
2. Exercise normal UI flows: open scene -> adjust background region/policy -> preview -> Apply/save -> render -> compare branch -> export -> reopen -> change tone -> reuse checkpoint. Confirm new settings survive and no obsolete result appears current.
3. Exercise cancellation, failed stage, corrupt checkpoint, missing dependency, concurrent edit and export failure. Retain prior successful renders and intact original sources.
4. Validate both pipeline and external TIFF precision and branch identity. Check that diagnostic artifacts are registered, discoverable and never mistaken for measured sources.
5. Record representative memory/runtime observations against the baseline; avoid retaining every large intermediate simultaneously. Investigate material regressions instead of adding speculative optimization machinery.
6. Reconcile every intermediary gap/modification entry from all phases: close with evidence or assign a documented durable disposition with reason and remaining acceptance. Deferred or blocked work is not completion. No anonymous TODOs or orphan phase lists may remain.
7. Update `docs/image_processing_architecture.md`, its diagrams, all changed schema/storage docs, user flows and requirement coverage. Verify cited papers support implemented variants and every adaptation is documented. Close all Phase 0A research tasks for delivered methods; no unresolved mathematical placeholder may be labeled implemented. Narrow historical overbroad coverage claims where necessary.
8. Produce a concise closeout report with implemented capabilities, intentional behavior changes, tests, human checks completed/pending, known limitations and the P2 candidate table below.

Completion statement must distinguish: automated implementation complete, real-scene verification complete, and user acceptance pending if applicable. If a required gate fails, continue fixing it; do not move work into P2 to obscure an incomplete prerequisite.

## 11. Phase 7 — selected P2 algorithms only

Status: WAITING FOR USER SELECTION; not a blocker to Phases 0-6.

| Candidate | Dependencies/selection questions to resolve once selected |
| --- | --- |
| Empirical PSF integration | Qualify existing helper, star rejection/centering, spatial adequacy, native sampling, kernel assets and UI |
| Regularized RL / deringing | Choose actual objective/update, signed-input policy, convergence, noise/halo metrics; use repaired masks |
| Residual registration | Common-source confidence, transform bounds, WCS/mask propagation and resampling policy |
| Same-band robust combination | Compatible band/unit/PSF grouping, independent ancestry, small-N behavior and uncertainty propagation |
| Residual debanding | Evidence of stripes and applicable geometry; never assume mosaic rows match detector axes |
| Wavelet denoising | Correlated-noise treatment, support boundaries, retained residuals and injected-feature preservation |
| Masked highlight protection | Persisted masks, transition/halo limits, demonstrated need beyond global GHS |
| Noise-based weighting | Prefer comparable same-band measurements; define variance semantics and provenance first |

P3/excluded proposals are not silently included. The user can select other features explicitly; first assess whether they broaden scope.

For each selection create a bounded subplan under `docs/compliance_status/`: purpose, input/output domain, stage location, requirements, changed contracts, mathematical reference, failure policy, UI flow, provenance/cache dependencies, fixtures, real-scene acceptance and closeout. Extend `docs/image_processing_architecture.md` with the selected method's primary references and complete mathematical definition before its implementation. Finish required infrastructure extensions as part of that selected algorithm, not in anticipation of all possible algorithms. Preserve Phase 6 gates and rerun affected/full validation after integration.

## 12. Verification commands and restart instructions

From the repository root, after confirming `.venv` and current test organization:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Focused examples (extend with newly added tests):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_fitsio.py tests/test_reprojection.py tests/test_planes_and_exports.py tests/test_mapping_tone.py tests/test_psf.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_scene_cards.py tests/test_scene_pipeline.py tests/test_pipeline_modes.py tests/test_ui.py -q -p no:cacheprovider
```

Disabling pytest's cache avoids previously observed junction-related cache warnings; it does not disable test assertions. Use the repository's current network opt-in policy and adapt commands only when the actual test layout changes.

At any handoff, record: completed phases, current exact task, files changed, new requirement IDs, passing/failing tests, artifact paths, pending user choices and first next command. Never restart by recreating completed work solely because a new chat lacks prior context.

### Suggested prompt for the next chat

> Implement `docs/compliance_status/image_processing_upgrade_implementation_plan.md` in order. Verify the current checkout and Phase 0 baseline, then complete the mandatory Phase 0A reference-backed `docs/image_processing_architecture.md` before foundation coding. Proceed through Phase 6 with requirements referencing that architecture, implementation, tests, UI verification and gap closeout. Preserve existing work and saved scene artifacts. P2 algorithms are not selected yet; leave Phase 7 pending until a selection is provided. Maintain status/evidence so another chat can resume without repeating completed phases.

## Plan preparation evidence

This planning pass read the existing P00 proposal, gap register and coverage baseline and used the preceding code-flow assessment. It created only this handoff document; it did not run implementation tests, alter requirements, modify runtime code, accept real-scene background regions or implement any phase. Before execution, verify all file/function names and assumptions against the current checkout.

## Bridge insertion before Phase 7 (2026-10-06)

After Phases 0-6, complete `reprojection_bridge_plan.md` through its final closeout
before P2 algorithm selection. Bridging is the next selected feature; no other P2
algorithm is selected by this amendment. Preserve completed foundation work.

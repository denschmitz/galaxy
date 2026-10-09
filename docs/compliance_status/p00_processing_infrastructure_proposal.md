# P00: processing infrastructure proposal

Date: 2026-09-28. Status: review complete; proposed requirements and implementation phases only. No runtime change is authorized or implemented by this document.

## Recommendation

Use dependencies, not priority labels alone, to sequence work. Start with a bounded P00 foundation and the P0 correctness fixes required to make it trustworthy. Then deliver a complete background/pedestal feature through save, render, diagnostics and reopen before expanding infrastructure for distant P2 algorithms.

Recommended progression:

1. P00-A/B: consistent image/support contracts and explicit processing boundaries, including affected P0 mask fixes.
2. P00-C/D: validated checkpoint lineage and one render path; preserve branch identity and export precision.
3. First P1 slice: shared sky-region diagnostics and masked pedestal correction for the Horsehead hypothesis, with the required persistence/UI integration.
4. Coverage policy and stable normalization references; then color-preserving tone, auto-stretch and GHS.
5. P2 algorithms individually where image evidence justifies them, adding variance/registration/stacking infrastructure at that point.

This avoids both repeatedly retrofitting masks/provenance and building a large unused algorithm framework. P00 is an enabling refactor; background modeling, common-coverage policy and color-preserving transforms still need their own accepted requirements.

## Review phases and observed baseline

| Review phase | Evidence/result |
| --- | --- |
| A: existing contracts | Inspected requirements, artifact storage spec, prior architecture baseline and known gaps |
| B: data flow | Inspected mapping, aligned FITS loading, pipeline reuse, scene input identity, provenance and direct-stack UI |
| C: dependencies | Identified minimal foundation and later algorithm-specific extensions |
| D: disposition | Findings mapped to proposed P00 work and acceptance below; no findings declared implemented |

Useful foundations already exist: `FITSPlane`, `ReprojectedPlane`, `CompositionResult`, immutable source files, explicit original/deconvolved branches, canonical scene execution, revision snapshots, render history, provenance, FITS stacks and footprints. Keep these concepts and evolve their interfaces.

Concrete weaknesses:

- `CompositionInputs` keeps arrays, metadata and optional footprints in separate dictionaries; a caller can omit support without an error.
- `compute_derived_planes` returns bare arrays, with no derived support or unit/ancestry result.
- `compose_channels_with_diagnostics` performs derived arithmetic, normalization, mapping and support aggregation in one function.
- `ui._render_aligned_planes` reads footprints but does not pass them into composition or tone.
- `load_multiplane_records` substitutes an all-ones footprint when no matching coverage exists. Its result does not carry a first-class WCS object, though exported headers contain WCS. Geometry must survive load, processing and re-export if future algorithms change alignment.
- The lower-level compose-only path finds stacks by filename and validates scene references; it does not compare an explicit stage producer key against all upstream inputs. It returns `output_wcs=None`. Existing scene-history safeguards are useful but are not stage-level compatibility validation.
- Scene identity is an explicit `INPUT_FIELDS` list. New processing settings must be added to effective inputs, frozen render inputs, validation and schemas; adding a processing function alone would leave stale-result risks.
- Provenance is structured around existing PSF/mapping/tone sections and plane summaries. There is no generic but typed record of each stage's inputs, resolved parameters, output artifacts and algorithm version.
- The current external export path re-encodes the registered PNG even for TIFF, while the pipeline separately creates a 16-bit TIFF.

## P00 changes

### Mandatory prerequisite: reference-backed processing architecture

Before foundation coding, create `docs/image_processing_architecture.md` under
Phase 0A of [the implementation handoff plan](image_processing_upgrade_implementation_plan.md).
It is the central supporting technical specification referenced by the normative
requirements: shared data/NaN/validity semantics, stage contracts, and selected
algorithms with primary references, defined mathematics, numerical behavior and
independent verification examples. Requirements retain authority over required
behavior; architecture decisions must trace to them. Complete the P00 definitions
before foundation implementation and each later algorithm definition before its
phase begins coding. User-unselected P2 algorithms remain deferred.

This prerequisite supersedes the earlier suggestion to scatter stage and
presentation mathematics across separate supporting specifications. Keep
checkpoint serialization details in their dedicated spec and link them from the
architecture. See Phase 0A for the required method template and completion gate.

### P00-A: make an image and its interpretation inseparable

Evolve the current dataclasses rather than introducing a parallel image hierarchy. The conceptual plane package should carry:

| Field | Purpose |
| --- | --- |
| Stable plane ID, source IDs and branch | Preserve identity independently of filename; distinguish repeat measurements and derived outputs |
| Floating values | Preserve native/calibrated signed samples until deliberate display conversion |
| Required valid mask | Mark which values may participate in statistics or spatial processing |
| Coverage/support | Retain fractional/geometric support separately from sample validity; never treat it automatically as inverse variance |
| WCS/grid identity | Define coordinates and sampling; validate agreement with array shape and other aligned operands |
| Unit and processing domain | Distinguish native/calibrated values, normalized display values and RGB; unknown units remain explicit |
| Metadata and parent lineage | Keep filter/instrument information and explain how the plane was produced |

Use one validity convention at processing boundaries (`True` means usable, for example); adapt the existing invalid-mask convention at ingestion. Explicitly document whether masks describe sample availability or algorithm support. Background-selection/source-exclusion masks are separate region objects and must not change the observation's validity mask.

At boundaries, validate dimensions, finite usable values and geometry. Same-grid operations preserve geometry; operations that change a grid return transformed data and masks together. Pure stages return a result without mutating their input arrays. Avoid unnecessary full-image copies: immutability is an ownership contract, not a requirement to duplicate every array at every stage.

Provide central helpers for valid statistics and masked arithmetic, but let each algorithm define its support rule. A ratio normally needs both numerator and denominator support and an explicit near-zero denominator policy; repeat-image combination can use the union of valid contributors. Do not impose one blanket intersection or union rule.

Known invalid-pixel leakage in PSF processing and derived-plane support loss must be fixed or explicitly rejected at the relevant interface. A wrapper around the existing unmasked RL implementation does not by itself make convolution mask-aware. Preserve scientifically valid negative residuals; an RL algorithm that cannot accept them needs an explicit input policy.

Defer full uncertainty ingestion/propagation to same-band combination or noise weighting. Reserve a documented extension point, but do not pretend optional variance exists or fill it with invented values.

### P00-B: separate physical samples, display normalization, RGB mixing and tone

Extract ordinary, typed functions from the current compositor. Keep a fixed ordered pipeline, with explicit optional calls and no dynamic plugin registry.

```text
Native plane package
  -> optional native corrections / qualified PSF branch
  -> reprojection
  -> aligned plane package + validated checkpoint
  -> optional aligned linear corrections / derived arithmetic
  -> per-plane display normalization
  -> display planes
  -> RGB mixing + per-channel support
  -> RGB tone
  -> floating display result
  -> format-specific encoding
```

This is a proposed set of interfaces, not an accepted algorithm ordering for every future correction. Detector corrections require suitable detector geometry. A pedestal can be estimated on an aligned sky region; correction before PSF processing instead has different dependencies and requires a separate explicit stage placement. Persist the chosen placement and frame rather than applying the same correction twice.

A stage result should contain its output image package, small diagnostics, and references to optional diagnostic products such as a background surface or residual map. Keep filesystem writes in orchestration/artifact code; numerical stages should not decide scene directories or update history.

Extract current behavior first with numerical equivalence tests. Changing two stretches into one, adopting luminance-preserving tone, or altering percentile defaults is subsequent feature work. These behavior changes must not be hidden inside the refactor.

### P00-C: make saved intermediates safe to reuse

FITS remains suitable for numeric arrays and WCS. Add a small versioned companion manifest for a checkpoint, recording schema version, domain, branch, parents, source content identities, grid, stage order, resolved upstream parameters, mask/region/kernel identities, algorithm versions and output checksums.

Two checks are needed: (1) a producer/dependency key proves the result corresponds to requested upstream processing; (2) an output checksum verifies integrity. A filename or a checksum of only the output is not sufficient for compatibility.

Changing downstream tone should not invalidate aligned samples. Changing the canvas, upstream kernel, source validity or an upstream correction must invalidate the affected checkpoint and downstream results. A correction after the aligned checkpoint can reuse it while recomputing composition; a native correction cannot.

Fail explicitly on incompatible or insufficiently described checkpoints. Legacy stacks should remain inspectable through a clearly identified import adapter, but must not be silently certified as reusable matches. Old scene recipes retain their effective numerical defaults; neither old files nor retained renders are silently migrated or overwritten.

Implement validation before considering automatic persistent caching of every stage. Initially keep the existing major checkpoint and selected diagnostic outputs. General scheduling, distributed execution, per-stage disk persistence and cache eviction are outside P00.

Use a centralized artifact path/registration layer consistent with the normative storage spec. GAP-STORAGE-001 remains open: new manifests/diagnostics need an explicit placement amendment; wholesale movement of historical directories is not a prerequisite and must not occur implicitly.

### P00-D: one rendering core, complete settings and honest output identity

Route canonical scene rendering and direct aligned-stack preview through the same numerical composition/tone core. The direct preview may retain a different explicit preset and lack archive provenance, but it must not discard masks. With identical inputs and settings both entry points should agree numerically.

Add new settings to both scene and processing models, JSON schema, execution translation, readiness, effective-input identity, render snapshots and provenance. Use typed stage-specific settings when features arrive; avoid an unrestricted dictionary of arbitrary processors. Stage records should distinguish requested settings from resolved auto-estimates.

An output result should identify preview PNG, high-depth TIFF, thumbnail and diagnostic files by role. External TIFF export must use the matching high-depth artifact, and the chosen branch must be passed explicitly. This prevents improved data from being reduced to preview precision at the final action.

Preserve background worker cancellation, current/stale detection, atomic scene-history commits and old-render immutability. New processing settings participate in those existing guards rather than bypassing them.

### P00-E: prove the boundaries, then ship one feature

Add contract tests and narrow end-to-end fixtures, not a large framework for hypothetical algorithms. Verify with the repository `.venv` and pytest. Use a frozen old recipe to distinguish intended bug fixes from accidental output changes.

Minimum fixtures: different native scales; masked bright outlier; NaN/zero padding; mismatched WCS; constant plane; ratio with missing or zero denominator; unequal band coverage; original/processed branches; checkpoint with modified upstream settings; 16-bit gradient with more than 256 distinct levels.

The first feature exercising the new interfaces should be per-filter sky diagnostics and optional pedestal subtraction over a persisted sky region. It directly addresses GAP-BG-001 and tests values, region masks, settings, diagnostic artifacts, reuse and human review together. A pipeline that merely accepts a dummy stage has not proved this workflow.

## Proposed atomic requirements and verification

These proposal IDs are local to this document. Promote accepted items into the normative requirements and coverage matrix before implementation.

| Proposal ID | Proposed requirement | Verification |
| --- | --- | --- |
| P00-01 | Every numerical image-stage input shall include explicit validity. | Reject missing/mismatched mask; invalid-value perturbation fixtures |
| P00-02 | Every image-stage output shall identify its sample domain. | Prevent display values from being consumed as linear calibrated inputs |
| P00-03 | Every aligned image-stage output shall preserve or explicitly replace its WCS. | FITS load/process/write round trip and changed-grid fixture |
| P00-04 | A stage shall not modify its input image values or masks. | Input-array checks before/after calls |
| P00-05 | A derived plane shall carry a validity result determined by its defined operand policy. | Missing operands, masked ratios and singular denominator cases |
| P00-06 | A checkpoint shall be reused only when its producer dependency key matches requested upstream inputs. | Parameter/source/kernel/region/grid invalidation matrix |
| P00-07 | A checkpoint shall pass its recorded integrity check before reuse. | Corrupted artifact rejection |
| P00-08 | New effective processing settings shall participate in render-input identity. | Edit/save/reopen/stale-render and concurrent completion tests |
| P00-09 | Each executed correction stage shall record its resolved parameters and parent identities. | Auto-estimate round trip and provenance comparison |
| P00-10 | Identical aligned inputs and settings shall produce equivalent results through scene and direct-preview entry points. | Numerical comparison including partial coverage |
| P00-11 | TIFF export shall select the matching high-depth render artifact. | More than 256 levels survive external export |
| P00-12 | Export shall use the explicitly selected render branch. | Original/processed export identity test |
| P00-13 | Legacy scene inputs shall retain their prior effective defaults when no new behavior is selected. | Existing scene golden recipe; separately enumerate intentional bug-fix differences |

Algorithm/version metadata must be stable enough for reproducibility. Do not rely solely on the existing hardcoded Galaxy version string. Define an implementation version or source revision policy for producer keys before reuse validation is claimed complete.

## Expected amount of code change

Planning estimates from inspected module responsibilities, not measured diffs or delivery promises. Ranges count touched Python source modules per independently delivered feature/phase; they overlap and must not be summed. Tests, schema and documentation changes are additional.

| Work | Expected impact | Why |
| --- | --- | --- |
| P00-A/B core contracts and separation | Medium-to-large refactor, approximately 6-10 modules | FITS, planes, mapping, tone, reprojection, PSF and orchestration interfaces change together |
| P00-C/D persistence and shared entry points | Medium-to-large integration, approximately 8-14 modules | Scene/schema translation, snapshots, checkpoint I/O, provenance, UI and exports must agree |
| P0 correctness after extraction | Usually 2-6 modules per defect; sometimes larger | Mask-aware convolution and coverage policies require real algorithmic decisions |
| P1 pedestal or GHS | Approximately 3-7 modules per feature after P00 | Main math becomes localized; settings, persistence, diagnostics and UI still need wiring |
| P1 coverage-aware composition/crop | Approximately 5-9 modules | Changes support policy, mapping, geometry/UI and persisted behavior |
| P2 empirical PSF / regularized RL | Approximately 4-8 modules | Kernel artifacts, qualification, native sampling and method-specific validation |
| P2 registration / same-band stacking | Approximately 6-12 modules | Changes WCS, multi-input ancestry, grouping and possibly uncertainty propagation |

P00-A/B and C/D together likely touch much of the roughly 15-20-module processing/persistence/UI surface, but do not imply replacing that code. Add small modules only where extracting an existing responsibility improves clarity; possible names such as `image_data`, `processing_stages` and `checkpoint_manifest` are illustrative, not requirements. Lines-of-code estimates would be premature until the accepted scope settles legacy checkpoint handling and PSF validity policy.

## Acceptance and final disposition

P00 is complete only when current algorithms run through the new contracts, disabled new stages preserve expected behavior, dependency/integrity checks reject unsafe reuse, scene save/reopen retains all inputs, cancellation/history protections pass, and the first accepted pedestal feature can use the interfaces without bypassing them. Stage corrections must preserve source files; diagnostics must remain distinguishable from scientific observations.

Known gaps consulted: cross-instrument GAP-COMP-001, GAP-STORAGE-001, GAP-PSF-MASK-001, GAP-PSF-SCALE-001 and GAP-BG-001. This review closes its analysis phases only. Validity/geometry omissions map to P00-A, compositor coupling to P00-B, lineage/storage to P00-C, divergent entry points/export to P00-D, and missing contract coverage to P00-E. None is claimed fixed. Existing algorithm-specific gaps stay open until their implementation and acceptance evidence exist.

No tests were run: this pass proposes design and records inspected code flow without changing runtime behavior. Future implementation must update `docs/design_requirements.md`, supporting schemas/specifications and `docs/testing/` traceability before compliance is claimed.

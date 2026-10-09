# Presentation bridge during reprojection

Status: pipeline, aligned support/checkpoints and UI implemented and technically
verified 2026-10-08; user full-scene presentation acceptance pending. Current
contracts: BRIDGE-MEDIAN-001 and BRIDGE-WIRE-002 in
[the algorithm document](reprojection_bridge_algorithm.md). Historical proposal
text below is superseded wherever those contracts settle a choice.
Requirements: REQ-BRIDGE-001 through REQ-BRIDGE-021. Workflow clarified 2026-10-06.

## Contract and interpretation

A bridge estimates missing native values for presentation. It does not recover
measured flux, prove saturation, or make the result suitable for scientific
photometry. Off means strict handling of missing samples, not certification of
all other processing for scientific analysis. Existing scene documents default
on; checkpoint identity must prevent reuse of a previous strict result as bridged.
Switching the setting invalidates aligned results and requires reprojection.
Native PSF processing remains governed by original observation validity. Prepare the original presentation copy automatically during selected-source loading
after archive-mask ingestion. Retain the untouched observational plane for native
PSF processing; prepare that branch independently after PSF processing and before
its reprojection. Neither branch consumes the other branch's estimates.
Scientific observational coverage remains separate from presentation support.
This refines MASK-001/REPROJECT-001 without treating estimates as observations.
The deferred PNG alpha proposal is not part of this change.

## Required switch and execution behavior

Use a scene-level boolean switch, "Bridge small NaN holes", in Scene refinement's
processing controls before rendering. Absent means On, including older scenes;
explicit False survives default resolution. No method picker or threshold sliders
are required for this delivery. The validated profile is typed, versioned,
recorded, and included in checkpoint keys. Phase 1 settles its persisted field.

A switch change edits the draft without launching processing. Save/reopen/duplicate
preserve the value; Generate preview persists the draft and snapshots the effective
setting before launch. Disable the switch during an active render. Show the
REQ-BRIDGE-019 explanation and mark older previews stale when settings differ.
The next full/reproject-only run automatically bridges selected sources during
loading. Download-only and metadata/footprint inspection do not create estimates.

Compose-only reuses matching aligned results without native loading or estimation.
Checkpoints retain observation support, presentation support, and estimate influence.
Old checkpoints missing bridge identity or required artifacts require reprojection,
including old scenes defaulting On. Off retains strict numerical processing.
Historical exports remain viewable with their recorded settings but must not be
labelled current after a toggle.

Eligibility rejection leaves a cluster invalid and records its reason. Unexpected
bridge failure aborts the render and must not be swallowed by the existing FITS-load
skip handler. An all-valid plane produces unchanged values and zero estimates;
an all-invalid plane produces no accepted clusters and retains no-support behavior.

## Algorithm specification

The [Native NaN bridge algorithm](reprojection_bridge_algorithm.md) is the
authoritative numeric/profile definition. BRIDGE-MEDIAN-001 replaces the earlier
harmonic suggestion and implements the user-discussed flat boundary-median fill.
The historical proposals below are retained as rationale, not competing defaults.

## Historical bounded eligibility proposal

These defaults are proposals requiring Phase 1 evidence, not settled numeric
requirements or implemented settings:

- Eight-connected invalid components; reject every label appearing on a border.
- Maximum native area 16 pixels and maximum width or height 8 pixels.
- Inspect a two-pixel valid boundary ring and a local background annulus extending
  from 8 to 16 native pixels outside the component bounding box.
- Require at least 75% of the boundary ring and 50% of the annulus to be valid.
- Require the boundary-ring 25th percentile to exceed annulus median plus five
  times robust noise (1.4826 times annulus MAD); reject an undefined or zero noise
  estimate rather than silently inventing a floor.
- Require brightness to decline outward in at least six of eight directional
  sectors, using specified valid-sample counts and comparison tolerances.

Brightness alone can identify holes in bright nebulosity; directional evidence
reduces that risk but must be tested. This is a conservative bright-core heuristic,
not an astronomical source classifier. Native-pixel limits are deliberately
simple and instrument dependent; angular or PSF-scaled limits are a later proposed
requirement if evidence shows they are needed. Phase 1 must settle precise sector
geometry, sample minimums, numeric tolerances, and accepted defaults before code.

## Implementation options

1. Historical harmonic alternative (superseded by BRIDGE-MEDIAN-001): label the invalid mask once with SciPy ndimage.label using an
   eight-connected structure. Gather border labels once; count label areas and
   obtain component bounding boxes. Reject exterior and oversized labels before
   local bright-core tests. Estimate only accepted holes in small patches using
   discrete harmonic interpolation (discrete Laplace equation with fixed observed
   boundary values). It produces smooth bounded estimates, not recovered peaks.
2. Same detector, inverse-distance weighted valid-neighbor interpolation. Simple
   and deterministic; define radius, weights, and tie handling. It may flatten or
   blur stellar cores. A nearest-valid seed from distance_transform_edt is fast,
   but nearest-neighbor fill alone can leave blocks or discontinuities.
3. Same detector, constrained local Gaussian/PSF fit. Can estimate a peaked core
   but adds model bias, parameter bounds, fit-failure behavior, and cost. Defer
   unless simpler interpolation fails presentation acceptance.
4. Adaptive bad_value_mode=ignore. A minimal experiment that renormalizes valid
   kernel weights and avoids strict NaN spread. Global ignore does not enforce
   size or bright-core eligibility and therefore cannot alone satisfy this
   contract. Selective blending requires aligned influence masks and extra
   resampling; compare its complexity with native patch filling.

No per-component path-to-edge search is necessary. Labeling and border-label
lookup process the grid once; local work is limited to retained small components.
A full-grid int32 label map costs about 492 MB for 8582 by 14340 pixels, before
masks and source arrays. Distance transforms with indices can cost substantially
more. Prefer patch-local transforms; benchmark actual peak memory rather than
assuming a full-grid transform is cheaper. Chunked labeling requires merging
components across chunk boundaries; add it only if measured memory requires it.

## Acceptance and verification design

- Pillars F090W source: native X=3727..3729, Y=6026..6027 (DS9 one-based)
  contains six NaNs; strict reprojection gives the observed 4 by 4 hole. Default-on
  must bridge it if the settled bright-core test accepts it, with finite output
  and recorded estimate influence. Off must reproduce the strict result.
- Synthetic border gaps, diagonal border connections, long thin trails, large
  enclosed holes, and holes in dark/flat nebulosity remain invalid.
- Finite observed zero, negative valid samples, rejected clusters, and all
  original source arrays remain unchanged by bridge preparation.
- Repaired samples never become observationally valid; influence survives aligned
  FITS save/load and compose-only reuse. Disabled or zero-weight bands do not
  contaminate downstream support decisions.
- Toggle/threshold/method changes reject stale checkpoints. Save/reopen preserves
  settings. Both reprojection methods and both branches follow the same contract.
- Native six-pixel fixtures, actual Pillars crops, and a full F090W mask benchmark
  bound correctness, runtime, and memory. No performance claim precedes measurement.

## Primary references

- SciPy label: https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html
- SciPy binary_fill_holes: https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.binary_fill_holes.html
- SciPy distance transform: https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.distance_transform_edt.html
- Reproject adaptive options: https://reproject.readthedocs.io/en/stable/reference/adaptive_options.html

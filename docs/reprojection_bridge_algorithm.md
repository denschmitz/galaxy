# Native NaN bridge algorithm

Date: 2026-10-07. Algorithm ID: **BRIDGE-MEDIAN-001**, version **1**.
This is the mathematical and data contract supporting REQ-BRIDGE-001..021.
Implementation/verification status belongs in
[the phased plan](compliance_status/reprojection_bridge_plan.md) and
[coverage matrix](testing/processing_upgrade_coverage.md).

## Decision and scope

The discussion in **Trace black dots to FITS masks** (chat
01a107fe-bfec-7732-82e4-cd525dd28062) accepted a flat stellar core rather than
inventing a smooth peak or inferred diffraction kernel. Use a constant median of
valid boundary values. **Plan NaN bridging feature** (chat
01a112f0-2b54-74f2-a367-c2127169b040) requires automatic selected-source preparation,
a saved default-On switch, and completion before P2 selection. This document
supersedes the later plan's harmonic-interpolation suggestion. Boundary P75, IDW,
harmonic interpolation, and PSF reconstruction are not automatic fallbacks.
Changing the estimator requires specification, version, and acceptance updates.

A fill is a presentation estimate in native linear units, not recovered flux or
a saturation diagnosis. Preserve observed diffraction structure outside the hole.
No per-star user intervention, empirical PSF, or unrelated P2 capability is needed.

## BRIDGE-INPUT-001: input and stage boundary

Input is a two-dimensional FITSPlane with values, observational validity, native
coverage, celestial WCS, units, branch, source identity and lineage. Ingestion
remains strict. Observationally valid finite zeros and negative values are valid
samples. Nonfinite values or invalid archive-mask support define candidates.

Prepare the original presentation working copy after selected-source ingestion
and filter eligibility. Retain the unchanged observation for PSF processing;
prepare its derived branch independently after PSF. Metadata inspection and
acquisition-only processing do not invoke the bridge. Off bypasses labeling and
estimation and passes the strict input values/support through unchanged.
Unexpected computation failures identify the source and fail; eligibility
rejections are normal counted outcomes, never a silent estimator fallback.

## BRIDGE-DETECT-001: candidate components

Let D be observed values and V the observed validity. Set
M = not(V and isfinite(D)). Label M once using scipy.ndimage.label with the
centrosymmetric 3 x 3 all-ones structure (eight connectivity). Background label
zero is not a candidate. Count all component areas using NumPy bincount. Gather
labels on all four image borders; a component with any such label is exterior,
including diagonal connections and paths extending outside a local patch.

Use scipy.ndimage.find_objects to obtain component bounding boxes. Reject exterior
and excessive-area components before local inspection. Reject a retained component
if either bounding-box width or height exceeds max_extent. Python loops are over
components and eight sectors only; each pixel operation uses NumPy/SciPy arrays.
Never compare a component label against the full image inside the component loop.

## BRIDGE-PROFILE-001: version-1 profile

The defaults below originate in the previous bounded proposal; the native Pillars
crop supports them. Regression and full-frame evidence must be retained before
feature closure. They are internal typed profile values, not additional UI controls.

| Parameter | Value | Meaning |
|---|---:|---|
| max_area | 16 | Inclusive maximum component pixels |
| max_extent | 8 | Inclusive maximum width/height |
| ring_radius | 2 | Eight-connected dilation radius around the actual component |
| annulus_inner | 8 | Inclusive inner Chebyshev distance from bounding box |
| annulus_outer | 16 | Inclusive outer distance and required patch margin |
| min_ring_fraction | 0.75 | Observed fraction of geometric ring |
| min_annulus_fraction | 0.50 | Observed fraction of geometric annulus |
| min_ring_samples | 12 | Observed ring sample minimum |
| min_annulus_samples | 64 | Observed annulus sample minimum |
| bright_sigma | 5 | Strict global brightness margin |
| min_sector_ring_samples | 2 | Observed ring samples per evaluable sector |
| min_sector_annulus_samples | 8 | Observed annulus samples per evaluable sector |
| sector_sigma | 1 | Strict outward-decline margin in background sigma |
| min_declining_sectors | 6 | Required sectors among eight |

All pixel/count limits must be positive integers, fractions in (0,1], sigma
multipliers finite and positive, ring_radius < annulus_inner <= annulus_outer,
and min_declining_sectors <= 8. Boolean values are not numeric limits. Invalid
profiles fail at construction. Numerical reductions use float64; values retain
input floating dtype. Tolerances do not convert an equality at a strict threshold
into acceptance.

## BRIDGE-EVIDENCE-001: bounded stellar-core evidence

The complete bounding box plus annulus_outer margin must lie in the native image;
otherwise reject as edge_patch. Do not clip rings or accept an incomplete annulus.
Use only original V samples, excluding every invalid component and every estimate.
Previously accepted clusters never become neighbors for subsequent clusters.

Let C be the local component mask. The geometric ring is
R = dilate_8(C, ring_radius) and not C.
For bounding-box endpoints x0..x1, y0..y1 (inclusive), define for each patch pixel

    d_box = max(x0-x, x-x1, y0-y, y-y1, 0)
    A = annulus_inner <= d_box <= annulus_outer

Require both valid fractions and sample minimums from the profile. On observed
annulus samples, define

    b = median(D[A and V])
    sigma = 1.4826 * median(abs(D[A and V] - b))

Reject nonfinite or nonpositive sigma as degenerate_noise; no artificial noise
floor is invented. Require the observed ring's linearly interpolated 25th percentile
strictly greater than b + bright_sigma * sigma. This is native-data evidence,
independent of display stretch, mapping weights, or per-filter normalization.

Partition R and A into eight equal angular sectors about the bounding-box center:

    theta = atan2(y-center_y, x-center_x)
    sector = floor(((theta + pi/8) mod (2*pi)) / (pi/4))

Sector zero points along positive x, with clockwise progression in image row
coordinates. A sector counts as declining only if it has both sample minimums and
its observed ring median is strictly greater than its observed annulus median
plus sector_sigma * sigma. At least min_declining_sectors must qualify. Missing
sectors do not count as passes. This rejects broad flat emission and simple ridges;
it is a conservative local heuristic, not a source classifier. An isolated compact
nebular knot can resemble a star; do not claim categorical discrimination.

## BRIDGE-FILL-001: constant neighbor estimate

For each accepted component, set f = median(D[R and V]), using float64 reduction,
then cast once to the input dtype and assign f to C by boolean indexing. Reject a
nonfinite cast as a preparation failure. No pixel outside C changes, including
finite zero and negative observations. The estimate lies between the minimum and
maximum valid ring observations (within dtype rounding). It intentionally cannot
recover a missing peak brighter than the ring. A solver is unnecessary.

The result retains the original observation package and returns separate values,
presentation support P = V or E, and estimate mask E. E is true only inside accepted
components, disjoint from V. V, archive-mask history, and native observational
coverage remain unchanged. Record candidate/accepted/estimated counts, rejection
counts by criterion, complete effective profile, algorithm ID/version, elapsed
seconds and conservative working-memory estimate. Rejection ordering is exterior,
area, extent, edge_patch, ring support, annulus support, noise, brightness, sectors.

## BRIDGE-ALIGNED-001: integration contract

These contracts gate later production pipeline integration; native numerical
implementation alone does not fulfill them.

Resample the derived values with presentation support, retaining the strict
observational result's support separately. Transport E with the same actual
positive interpolation/adaptive kernel geometry, including its nonzero taps;
nearest-neighbor mask resampling does not satisfy estimate influence. Kernel
influence applies to any usable output receiving estimated input, even where a
strict result is also finite. For influence transport, do not apply physical-flux
Jacobian scaling to a normalized binary mask. Reject nonfinite/unsupported output
instead of interpreting stored zero as a measurement.

Aligned plane packages shall explicitly carry observational support, presentation
support, and kernel estimate influence. Legacy packages may default these fields
only for historical inspection. Certified checkpoint reuse requires the new fields
and current bridge dependency identity, including Off. Single-plane aligned FITS
and stacks persist OBS_SUPPORT, PRESENT_SUPPORT and ESTIMATE_INFLUENCE extensions
with GALTYPE and PARENT identification, paired with unchanged value/WCS/lineage
contracts. Checkpoint checksums cover the entire stack and summaries certify all
three fields. Compose-only validates these artifacts without native preparation.

Background/black/white/noise statistics and empirical PSF measurement use observed
support excluding influenced outputs. Rendering/output support may use presentation
support. Derived combinations require presentation support from every nonzero
contributor and union their influence; observational support requires all observed
contributors. Ratios also require a supported nonzero denominator. Disabled and
zero-weight contributors do not affect support/influence. Channel display support
unions active contributions; tone statistical support excludes active estimate
influence. Preserve the current coverage-policy contract and truthful source ancestry.

Persist scene `bridge.enabled` as a strict boolean, absent resolves to true.
Effective inputs, execution translation, render snapshots and provenance include
it; producer keys include the full profile/version. Toggle marks aligned results
stale. The existing render/save/reopen/duplicate/export flow must be verified,
including active-render locking, before GAP-REPROJECT-BRIDGE-001 closes.

## BRIDGE-VERIFY-001: acceptance cases

1. Exact source crop in tests/fixtures/reprojection_bridge/pillars_f090w_core.fits:
   source 8582 x 14340; DS9 X=3727..3729, Y=6026..6027. Six invalid samples,
   zero WHT and zero CON. JSON records source/crop hashes and coordinates. Real
   profile measurements: ring Q25 363.011322, median 489.006088; annulus median
   13.233116, sigma 8.241226; all eight sectors decline. Fill those six pixels
   with float32 489.006088, preserving all other samples and observed validity.
2. Exact median known-answer ring, even-count median convention, signed/zero valid
   samples, and only-invalid assignment. Reject bright outliers as determinants
   of the median; no fill from another bridge estimate.
3. Exterior/diagonal paths, excessive area/extent, edge patches, dark/flat emission,
   inadequate ring/annulus samples, zero-MAD background, directional ridge.
4. All-valid/all-invalid planes; strict Off bypass; invalid profiles; deterministic
   repeat runs; preparation failures propagate with source identity.
5. Both branches and both resamplers; full influence transport and certified FITS
   round trip; stale/corrupt/missing-mask reuse rejection; full UI persistence.
6. Native labeling and preparation on the full source dimensions, followed by
   both-method/branch and UI evidence at integrated closeout. Benchmark before
   optimizing; never add chunking solely on predicted speed.

Initial native benchmark acceptance: elapsed <= 60 seconds and process peak <=
6 GiB peak working set (resident memory) on the recorded development host for one 8582 x 14340 source, including
observational package and presentation result. Incremental conservative estimate:
24*N + 256*(K+1) + 1 MiB bytes, where N is native pixels and K candidate labels;
includes int32 labels, possible int64 bincount conversion, copies/masks and
component bookkeeping. Report resident and committed process peaks and baseline separately; the estimate
is not a measured allocation. Later resampling budgets must include native result
retention, kernel mask passes, both-branch retained arrays and output WCS workspace;
these remain an integration gate, not a completed performance claim.

## Primary references and project adaptations

- [SciPy label](https://docs.scipy.org/doc/scipy-1.15.2/reference/generated/scipy.ndimage.label.html): explicit eight-connected structure and int32 output.
- [SciPy find_objects](https://docs.scipy.org/doc/scipy-1.15.2/reference/generated/scipy.ndimage.find_objects.html): bounded component slices.
- [SciPy binary_dilation](https://docs.scipy.org/doc/scipy-1.15.2/reference/generated/scipy.ndimage.binary_dilation.html): local ring geometry.
- [NumPy median](https://numpy.org/doc/2.2/reference/generated/numpy.median.html): constant boundary statistic, including even-count averaging.
- [NumPy percentile](https://numpy.org/doc/2.2/reference/generated/numpy.percentile.html): explicit linear Q25 convention.
- [NumPy bincount](https://numpy.org/doc/2.2/reference/generated/numpy.bincount.html): component counts.
- [Reproject adaptive source](https://github.com/astropy/reproject/blob/v0.15.0/reproject/adaptive/core.py) and [interpolation source](https://github.com/astropy/reproject/blob/v0.15.0/reproject/interpolation/core.py): actual installed kernel contracts.

Eight connectivity, threshold/profile values, directional sectors and support
separation are Galaxy adaptations. These references document operations; they do
not establish the astrophysical correctness of this heuristic or estimated flux.

## BRIDGE-WIRE-002: integrated representation and influence (2026-10-07)

`ReprojectedPlane.valid` and `footprint` retain strict observational resampler
support. `presentation_support` is a float32 aligned footprint and
`estimate_influence` is a boolean aligned mask. `presentation_valid` requires
finite values and positive presentation support; `statistics_valid` requires
observational validity and excludes estimate influence. Observation support is
contained in presentation support. Estimate influence is restricted to usable
presentation outputs. These invariants are validated on construction/load.

For an accepted native hole, perform strict observational and presentation value
resampling separately. Apply the identical kernel/WCS/boundary settings to an
indicator equal to one on native estimates, zero on observations, NaN on rejected
invalid samples; disable flux scaling for this indicator. Positive finite mask
output marks kernel influence, with no nearest-neighbor approximation or positive
threshold tolerance. Both installed kernels are positive (bilinear/Gaussian).
No estimates means one strict value pass and an all-false influence mask.

Single-plane and stack files declare `SUPVER=1`; support extensions use GALTYPE
`OBS_SUPPORT`, `PRESENT_SUPPORT`, `ESTIMATE_INFLUENCE`, and exact `PARENT`. Existing
FOOTPRINT/VALIDITY extensions remain readable. OBS_SUPPORT stores observational
validity (uint8), PRESENT_SUPPORT stores the float32 presentation footprint, and
ESTIMATE_INFLUENCE stores uint8. Bridge diagnostics are JSON in the value header
BRMETA. Modern stacks missing declared support fields fail; legacy inspection can
adapt missing fields, but certified reuse requires versioned support artifacts.
Checkpoint format 2 includes all support counts and per-mask hashes, full-stack
integrity, bridge enablement/profile/version, and version-2 resampler/aligned IDs.
Format-1 manifests require full/reproject-only regeneration even with Off.

Scene bridge enablement is an optional strict-boolean model field, resolving true
when absent. Effective inputs normalize absent and explicit true equivalently;
new successful snapshots explicitly record the effective bridge state. Historical
snapshots without bridge metadata remain loadable, but cannot certify a current
bridged preview/export. This preserves old revision identity without falsely
labeling old strict outputs as bridged. Existing history remains immutable.

Normalization statistics, source-masked background sampling, and tone statistics
exclude influenced outputs. The same observed transform is applied to all usable
presentation values. Subtract applied background pedestal on presentation support,
while retaining observation support/influence. Composition carries separate display
and statistics masks; common output support uses required presentation masks and
common tone reference uses required observed, uninfluenced masks. Disabled and
zero-weight operands contribute to neither mask.

Integrated benchmark budget: <=120 seconds per resampler and <=16 GiB peak resident
memory for the full F090W source prepared then projected onto a 512 x 512 local
canvas on this recorded host. This tests full native mask/input allocation and
both kernels; it does not predict time for an arbitrary user-selected canvas.
Include retained observation/presentation arrays and additional indicator/strict
resampling workspace in the pipeline estimate. Full-scene dimensions and branch
settings remain explicit provenance inputs rather than a universal speed claim.

# Galaxy image-processing architecture and mathematical specification

Revision: 0.2, 2026-10-03. Status: Phases 0-6 implemented and verified.

## 1. Authority, scope, and notation

`docs/design_requirements.md` is normative. This document is the supporting
technical specification for the processing behavior cited by those requirements.
It does not authorize a feature that the requirements do not require. Sections
through Phase 5 define implemented behavior. Phase 7 algorithms have insertion
points only and remain unselected.

Symbols used below:

- `x[p]`: a floating sample at pixel `p`.
- `V[p]`: boolean observation validity; `True` means the sample may participate.
- `C[p]`: finite coverage in `[0,1]`; geometric/fractional support, not variance.
- `S[p]`: an operation-specific support mask.
- `W`: celestial WCS plus raster shape; together they define a grid.
- `H` and `H^T`: PSF convolution and adjoint convolution.
- `q_a(X)`: percentile `a` over the specified valid sample set `X`.
- `eps`: a named positive numerical guard, never a substitute for validity.

Processing domains are `native_linear`, `aligned_linear`, `display_plane`, and
`display_rgb`. “Linear” describes the arithmetic domain; it does not assert that
different filters are physically interchangeable. Normalization is a display
operation, not calibration.

```text
FITS -> native package -> optional native PSF branch -> reprojection
     -> aligned package/checkpoint -> optional aligned correction -> arithmetic
     -> display normalization -> RGB mixing -> RGB tone -> format encoding
```

Original and processed branches never converge into one sample set. A checkpoint
boundary is after reprojection and before optional aligned corrections. Numerical
stages do not write files or mutate scene history.

## 2. Shared contracts

### IMG-CONTRACT-001 — image package (target)

Every numerical image-stage operand is one immutable-by-contract package with:

| Field | Contract |
| --- | --- |
| `plane_id` | stable logical identity, independent of filename |
| `values` | 2-D floating array; signed finite values are preserved |
| `valid` | required boolean array, same shape; `True` means usable |
| `coverage` | required float array, same shape, finite in `[0,1]` |
| `wcs` / `grid_id` | celestial WCS and deterministic identity including shape |
| `unit` | explicit string or explicit unknown value |
| `domain` | one of the declared domains |
| `branch` | `original`, `deconvolved`, or a later specified branch |
| `source_ids` | ordered stable source identities |
| `parent_ids` | ordered immediate parent identities |
| `metadata` | preserved non-contract metadata; it cannot override typed fields |

Construction fails when arrays are not 2-D or shapes differ; `coverage` is
nonfinite or outside `[0,1]`; a `True` validity entry has a nonfinite value; WCS
does not describe two celestial pixel axes; or declared grid identity disagrees
with WCS/shape. Finite values under `valid=False` are uninterpreted fill and may be
zero. Consumers must not inspect them as observations.

Same-grid operations require equal shape and numerically equivalent pixel-to-sky
transforms within `1e-9` degree at the four pixel corners and reference pixel.
They preserve WCS and grid identity. Grid-changing stages return values, validity,
coverage, and a new WCS together.

The package owns no promise of a writable copy. Stages must not mutate input
arrays. Read-only views may be shared; a stage allocates output only when needed.

### MASK-001 — validity, coverage, and regions (target)

Validity answers “may this sample participate?” Coverage answers “how much of this
output sample is geometrically supported?” A selection region answers “was this
sky location chosen for an estimate?” A source-exclusion region answers “should
this otherwise valid sample be excluded from that estimate?” These are distinct.

At ingestion:

`V = finite(x) AND (DQ == 0 when applicable) AND (WHT > 0 and finite when
applicable) AND (any CTX sample != 0 when applicable)`.

The current invalid-mask representation is inverted exactly once by its adapter.
NaN is never a black measurement. At an external boundary that stores zero-filled
values, `V` is mandatory and authoritative. Valid zero and valid negative values
remain measurements. Statistics use `x[V & region & ~exclusion]` only.

Coverage is positive geometric support produced by ingestion/reprojection.
`V_out` may additionally require `C_out > 0`, but `C` is never interpreted as an
inverse variance or multiplied into a sample merely to make it “more valid.” Each
algorithm defines whether operand support is intersection, union, or sensitivity.

### STAGE-001 — pure numerical stages (target)

A stage receives typed packages and settings and returns:

1. typed output package(s);
2. small scalar/tabular diagnostics;
3. optional diagnostic-product values for orchestration to persist; and
4. a stage record conforming to PROV-001.

Stages validate all inputs before calculation, do not mutate inputs, perform no
filesystem writes, and fail explicitly on unsupported domains, units, geometry,
or insufficient support. Scene rendering and direct aligned-stack preview call the
same stage functions. Entry-point presets may differ and are recorded inputs.

### NUM-001 — shared numerical rules (target)

- Internal arithmetic is float32 or float64 as specified by the method. Reductions,
  percentiles, checksums, and GHS evaluation use float64.
- Empty support is an error unless a method explicitly returns an unsupported
  result. A constant percentile interval is a degenerate result; legacy mode may
  use the documented `1e-6` interval, while new modes must expose the degeneracy.
- Division validity requires `abs(denominator) > denominator_threshold`; adding
  epsilon to a denominator does not make a singular sample valid.
- Nonfinite values are invalid at the next boundary. A stage that produces a
  nonfinite value at a location expected valid fails with the stage and plane ID.
- Clipping is allowed only at a specified display/gamut or encoding boundary.
- Unless a method states otherwise, comparisons use `rtol=1e-6`, `atol=1e-6` for
  float results and exact equality for masks, identities, and encoded integers.

## 3. Current and corrected methods

### INGEST-001 — FITS image and mask ingestion (target)

Purpose: convert one selected two-dimensional FITS science image into
`native_linear`. Select the first image-bearing `SCI` or `PRIMARY` HDU in file
order, otherwise the first image-bearing HDU. Require a two-dimensional celestial
WCS. Values are float32 in the declared `BUNIT`, or explicit unknown unit.

Apply MASK-001 using same-shape DQ/WHT extensions. CTX may contain leading context
axes and is valid where any context sample is nonzero. Record the mask extension
names and input valid fraction. Initial coverage is `1.0` where valid and `0.0`
where invalid. Preserve source content identity and selected HDU identity.

Known-answer cases: valid zero and negative values remain valid; changing any
finite value under `valid=False` does not change later valid statistics; malformed
dimensionality and missing celestial WCS fail.

### PSF-GAUSS-001 — sampled circular Gaussian kernel (target)

Purpose: create a pixel-sampled approximation of a circular sky Gaussian for the
existing RL option. Input FWHM `f > 0` is in arcseconds. For orthogonal celestial
pixel axes with scales `s_x,s_y` arcsec/pixel:

`sigma_x = f / (2 sqrt(2 ln 2) s_x)` and
`sigma_y = f / (2 sqrt(2 ln 2) s_y)`.

Sample `k[i,j] = exp(-0.5*((i/sigma_y)^2 + (j/sigma_x)^2))` over each axis through
`ceil(4 sigma)` and normalize in float64 so `sum(k)=1` within `1e-12`. Reject a
nonfinite/nonpositive FWHM, degenerate pixel scale, or non-orthogonal/skewed pixel
geometry above `1e-6` relative dot-product tolerance. Image rotation is supported:
a circular sky Gaussian is invariant under rotation. A supplied kernel must be
finite, two-dimensional, nonnegative, have positive sum, have odd dimensions, and
carry or be explicitly qualified for the native sampling.

Known-answer: FWHM `0.2` arcsec produces twice the pixel sigma at `0.1` arcsec/pixel
as at `0.2` arcsec/pixel. The anisotropic fixture produces the corresponding
elliptical pixel kernel.

### PSF-RL-001 — validity-aware Richardson–Lucy (target correction)

Purpose: retain the required Richardson–Lucy branch without allowing invalid
observations to influence valid output. This is unregularized RL; the current
post-update blend called `regularization` is not a published regularized objective
and is not part of this corrected method.

Assumptions: valid observations and the initial estimate are finite and
nonnegative; kernel meets PSF-GAUSS-001/supplied-kernel rules. If any valid sample
is negative, fail with an actionable signed-input error. Do not clip it silently.

Let `M` be `1` for valid observations and `0` otherwise, `y=M*x`, normalized PSF
`h`, and sensitivity `a=H^T(M)`. Initialize `f_0=max(y, eps)` on valid pixels and
zero elsewhere. For iteration `n`:

`r_n[p] = M[p] * y[p] / max((H f_n)[p], eps)`

`f_(n+1)[p] = M[p] * f_n[p] * (H^T r_n)[p] / max(a[p], eps)`.

Use zero padding for `H` and `H^T`; sensitivity normalization corrects the missing
observation/boundary mass. Output validity is the input `V`; output coverage and
WCS are unchanged. Output outside `V` is zero fill. Stop after the persisted
integer iteration count in `[1,100]`; no data-dependent early stop is used in this
phase. `eps=1e-6` in the image's numeric scale for legacy compatibility and must be
recorded. Stage diagnostics include iteration count, kernel identity, sensitivity
minimum over valid samples, and min/max output.

This discrete masked adaptation follows the Richardson/Lucy multiplicative update
and explicitly normalizes for missing observations. It is a Galaxy adaptation;
the original papers assume nonnegative frequency distributions rather than this
validity mask. Verification perturbs invalid samples by extreme finite values and
requires identical valid output within NUM-001 tolerance.

### REPROJECT-001 — common-grid resampling (target)

Purpose: transform one native package to the configured celestial grid. Before the
library call use NaN at invalid input locations. Interpolation uses the reproject
interpolation algorithm. Adaptive mode uses adaptive resampling with
`conserve_flux=True` only when the configured policy and declared unit semantics
qualify the input as flux per pixel; a surface-brightness unit such as MJy/sr must
not silently receive flux-per-pixel scaling.

The library footprint is clipped to `[0,1]` after rejecting nonfinite values.
`V_out = finite(x_out) & (C_out > 0)`. Store zero fill under invalid output. Output
is float32 with the exact configured WCS and shape. Record algorithm name, library
version, flux/surface-brightness interpretation, input/output grid identities, and
coverage fraction. A wrong or noncelestial grid fails.

Reference behavior follows the official `reproject` algorithm and adaptive-option
documentation cited in section 8; in particular, interpolation is not guaranteed
photometrically accurate and adaptive `conserve_flux` assumes flux-per-pixel data.

### ARITH-001 — derived linear combination and ratio (target)

All operands must be `aligned_linear` on the same grid. Zero-weight operands do not
participate in support or unit checks.

For `z=sum(w_i*x_i)`, `V_z` is the intersection of validity for nonzero-weight
operands. Coverage is their minimum. Values are evaluated only under `V_z`.
Compatible equal units are preserved. Addition of known unequal units fails;
unknown units produce explicit unknown output with a warning only when the
requirements allow the operation.

For ratio `z=N/D`, build `N` and `D` by the same rules. Then
`V_z=V_N & V_D & finite(N) & finite(D) & (abs(D)>threshold)`. Coverage is the
minimum of numerator and denominator coverage. Output is dimensionless only when
known numerator and denominator units are compatible; otherwise fail. The
persisted positive threshold replaces the current `D+epsilon` behavior. Parent IDs
include every nonzero-weight operand in stable order.

### NORM-LEGACY-001 — legacy plane display normalization (target extraction)

This method preserves REQ-NORM-002/003 behavior for existing recipes. For `native`,
copy valid values, use zero fill elsewhere, then apply nonnegative gain. For
`percentile`, calculate `b=q_black(x[V])`, `w=q_white(x[V])`; legacy degeneracy
sets `w=b+1e-6`. For valid samples:

`u=clip((x-b)/(w-b),0,1)`.

Then apply one selected stretch:

- linear: `t(u)=u`;
- asinh: `t(u)=asinh(a*u)/asinh(a)`, `a>0`;
- gamma: `t(u)=u^(1/g)`, `g>0`.

Output is `display_plane`, unitless, with unchanged support/grid and recorded
resolved `b,w`, percentiles, stretch, gain, and valid fraction. This stage is not
physical calibration.

### RGB-MIX-001 — weighted RGB mixing (target extraction)

Input packages are same-grid `display_plane` values. For channel `c`,
`R_c[p]=sum(w_ic*x_i[p])` over nonzero mapped weights whose operands are valid at
`p`. Current legacy support is the union of valid nonzero-weight contributors for
that channel. Missing operands contribute numeric zero only under the paired
support mask; the zero is not labeled a measurement. Return float RGB planes,
per-channel validity, per-channel coverage diagnostics, and absolute-signal
contribution diagnostics. Negative weights remain allowed.

### TONE-LEGACY-001 — legacy independent-channel tone (target extraction)

For each RGB channel independently, compute black/white percentiles over its valid
support, normalize and clip as in NORM-LEGACY-001, apply configured asinh or gamma,
then channel gain and bias. Set unsupported samples to zero. Saturation uses the
arithmetic RGB mean `L=(R+G+B)/3` and `L+s*(RGB-L)`, followed by `[0,1]` clipping.
The result is `display_rgb` scaled to `[0,65535]`. Empty channel support fails.

### ENCODE-001 — display encoding and export identity (target)

The floating display result is encoded once per role. Preview PNG divides the
`[0,65535]` values by 257 and quantizes to uint8 RGB. High-depth TIFF clips and
quantizes directly to uint16 RGB. Thumbnail derives from the preview PNG.
External PNG export selects the registered preview role; external TIFF export
selects the registered high-depth TIFF role. Both require an explicit branch and a
render matching current effective inputs. A missing requested role fails; no
cross-format re-encoding is an allowed fallback. The uint16 fixture must retain
more than 256 distinct levels after export.

## 4. Persistence, identity, and provenance boundaries

### CHECKPOINT-001 — aligned checkpoint contract (Phase 2 outline)

The detailed wire format belongs to `docs/processing_checkpoint_spec.md`. A
checkpoint is reusable only when both conditions pass:

1. a canonical producer dependency key matches source content identities, native
   validity identity, branch, canvas/grid, ordered upstream stages, kernels/regions,
   resolved upstream parameters, and algorithm implementation versions; and
2. every referenced output passes its recorded SHA-256 integrity check.

Tone and post-checkpoint corrections are excluded from the aligned producer key.
Canvas, source bytes/validity, native kernel, or native correction changes are
included. A legacy stack without the manifest is inspectable through an explicit
adapter but is not a certified reusable checkpoint.

### IDENTITY-001 — scene effective inputs (target)

Every persisted processing setting that can change numeric output is part of the
scene's effective-input identity, render snapshot, readiness checks, schema, and
current/stale comparison. Runtime logging/progress policy is excluded. Requested
auto behavior and the resolved numbers are both persisted; reopen never silently
re-estimates a successful render's settings.

### PROV-001 — stage record (target)

Each executed stage records stable stage and algorithm IDs; implementation version
or source revision; ordered parent IDs; branch; input/output domains, units, grid
IDs, validity/coverage summaries; requested settings; resolved settings; diagnostic
asset IDs; and output content identities. A hardcoded application version alone is
not an algorithm version. Stage records are assembled by orchestration and do not
authorize the numerical function to write files.

### COMPAT-001 — compatibility and failure policy (target)

Revision-one scenes that omit new sections retain current effective defaults.
Disabled new features are numerically equivalent to the Phase 0 frozen recipe,
apart from enumerated validity, ratio, PSF, direct-preview, checkpoint, and export
correctness fixes. Old files and retained renders are never silently rewritten.
Strict compose-only rejects missing/incompatible checkpoints and reports the
required rebuild; full mode may build a new immutable run.

## 5. Phase 3 background methods

These definitions are normative for the bounded Phase 3 pedestal feature. They do
not authorize gradients, polynomial surfaces, linked-filter models or debanding.

### BG-PED-001 — masked constant pedestal

Estimate each plane over one common sample mask formed from the union of persisted
ICRS inclusion rectangles, minus the union of persisted ICRS exclusion rectangles,
intersected with finite validity and positive coverage for every participating
plane. Rectangle membership is evaluated at pixel centers. For a rectangle center
`(ra0, dec0)`, wrapped longitude difference is multiplied by `cos(dec0)`; a pixel
is inside when the absolute tangent-plane longitude and latitude differences are
no greater than half the stored width and height. Boundaries are inclusive.

The estimator is a deterministic iterative sigma-clipped median in each plane's
native aligned unit. Defaults are clip sigma `3.0`, at most `5` iterations,
minimum `256` common samples and minimum common-valid fraction `0.5` relative to
the geometric region after exclusions. At each iteration, compute median `m` and
`s = 1.4826 median(|x-m|)` over retained samples and retain samples satisfying
`|x-m| <= clip_sigma*s`. Stop when membership is unchanged, `s` is zero, or the
iteration limit is reached. Nonfinite values are never samples. If either minimum
is unmet before or after clipping, return `insufficient_samples`; do not invent a
pedestal. The resolved pedestal is the final median.

Estimation is an explicit proposal. Canonical rendering never silently estimates:
`pedestal` mode requires persisted resolved records matching the region/estimator
selection key, plane ID, source IDs, branch and grid. Subtract the scalar from all
valid samples in that plane, including protected-source pixels excluded only from
estimation. Invalid storage values remain zero. Preserve signed residuals,
coverage, WCS, branch, source/parent identity, and the pre-correction checkpoint.

Diagnostics: geometric sample count, common-valid count/fraction, final sample
count, median, robust MAD-derived spread, rejected count, resolved pedestal and
residual median. MAD is a robust spread diagnostic, not automatically detector
noise. The known-answer fixture uses NumPy seed `20260928`, Gaussian noise,
at least 16,384 geometric samples, masked padding/outliers and an excluded diffuse
source. Its pedestal error shall not exceed `0.1` input-noise sigma and corrected
diffuse-source integrated signal error shall not exceed one percent.

### NORM-BG-001 — background-referenced black policy

`legacy_percentile` preserves the prior two percentile normalizations.
`corrected_zero`, available with pedestal mode, fixes every corrected plane black
reference to native zero while retaining its configured white percentile. After
RGB mapping, linear combinations of those zero references are still zero, so the
channel-tone black reference is also fixed to zero while its configured white
percentile remains. Neither stage recomputes a black percentile. Clipping negative
residuals occurs only at the explicit display-normalization boundary; aligned
corrected packages retain them. Zero/unsupported output samples remain zero.

## 6. Implemented Phase 4-5 methods

### COVERAGE-001 — presentation support policy

`available_contributors` preserves RGB-MIX-001 union support and is the backward-
compatible default. `common_required_bands` forms the logical intersection of
finite-valid, positive-coverage masks for every enabled mapping with a nonzero RGB
weight. A mapped derived plane contributes all of its nonzero source dependencies
to the required identity set; its own operation-specific valid mask also
participates. Output support and tone-statistics support are independent. The
accepted recommended policy is union output with common-required-band tone
statistics. Existing omitted settings retain union output with output-support
statistics.

An empty intersection is an error whenever common support is selected for output
or tone statistics. Every disconnected supported component is
retained, and internal holes stay unsupported. No implicit largest-component rule
exists. `crop=none` preserves the original raster. `crop=bounding_box` uses the
inclusive bounding rectangle of all selected output-support pixels, expands all four sides
by `padding_pixels >= 0`, clips to the input raster, and slices WCS with the same
`(y, x)` slice. With common tone reference, percentile bounds are resolved on the
uncropped common mask and then applied unchanged to every output-valid channel
sample. Partial-support pixels are not divided by contributor count and receive no
local gain compensation. Crop and padding are presentation geometry only.

Diagnostics contain both policies, crop and padding; stable required plane and source
IDs; union/common/excluded pixel counts; common/union fraction; 8-connected
component count; tone-reference pixel count; zero-based half-open crop bounds
`[x0,y0,x1,y1]`; and output shape.

### NORM-REFERENCE-001 — stable references

`percentile` is the legacy per-render mode. `fixed_bounds` uses persisted finite
native-domain `black_value < white_value`. A region-derived proposal uses the
persisted Phase 3 ICRS inclusion and exclusion geometry, common finite-valid
positive-coverage samples, and requested percentiles to resolve fixed bounds for
each selected plane. Constant, empty, mismatched-grid, or identity-stale samples
fail without fallback.

Applying a proposal stores a locked reference with a stable reference ID, region
IDs, branch, grid ID, source IDs, native unit, coverage policy, requested
percentiles, resolved values, sample count, low/high clipping fractions, and
`locked=true`. Rendering consumes only the resolved fixed bounds. Viewport, crop,
padding, and subsequent pixel-content changes do not silently recompute them;
`Recompute` is an explicit proposal-and-Apply operation that replaces the reference
and makes downstream renders stale.

### TONE-SHARED-001 — shared-intensity stretch

Input is the three unitless output channels after percentile/fixed-bound
normalization and then configured gain and bias. Unsupported channel samples are
represented by zero and remain invalid in that channel; the intensity definition
is nevertheless always `L=(R+G+B)/3`, so partial coverage receives no
contributor-count compensation. A supported negative channel is an error.

For a selected monotone curve `T:[0,1]->[0,1]`, use `m=T(L)/L` when
`L>eps`, where `eps=1e-12` in float64, and set the output vector to zero when
`L<=eps`. The same multiplier is applied to all supported channels. This preserves
positive channel ratios before gamut handling. `clip` independently clips channels
to `[0,1]`; `rescale` divides the pixel vector by its maximum when that maximum
exceeds one. Ratio preservation is claimed after `rescale`, but not after `clip`.
Saturation adjustment follows gamut handling. Independent per-channel tone remains
the compatibility default.

### AUTOSTRETCH-001 — deterministic shared-asinh proposal

The proposal input is the linear shared-intensity image produced with per-plane
normalization, tone gain/bias, and no main stretch. Its sample mask is the common
valid mask inside the persisted background inclusion rectangles and outside the
persisted exclusions. The background selection key, branch, grid and source IDs
form the reference identity. The minimum sample count is the persisted background
estimator minimum, never less than 256.

Let `q50` be the sample median, `s=1.4826*median(|x-q50|)`, and
`f_obj=count(x>q50+3s)/N`. Reject nonfinite input, `s<=1e-12`, `q50<=1e-12`,
`q50>=0.1`, or `f_obj>0.25`. The requested target is `T(q50)=0.1` for
`T(x)=asinh(a*x)/asinh(a)`. Resolve the unique `a>0` by 80 bisection iterations
over `[1e-6,1e6]`; fail if the target is not bracketed. Record `q50`, `s`,
`f_obj`, sample count, target, resolved `a`, and the fractions of supported RGB
channel samples below zero and above one before gamut handling. A confidence label
is `high` when `N>=4096` and `f_obj<=0.05`, otherwise `qualified`.

Preview and Recompute only produce this proposal. Apply persists the resolved
shared asinh method and locked proposal record. Reopen consumes those values and
does not re-estimate them.

### TONE-GHS-001 — Generalized Hyperbolic Stretch, forward GHS subtype

The authoritative candidate is GeneralizedHyperbolicStretch process documentation
version 3.0.4. Its input control `ln(D+1)` maps to `D=exp(control)-1`; parameters
include local intensity `b`, symmetry point `SP`, shadow protection `LP`, and
highlight protection `HP`, with `0<=LP<=SP<=HP<=1`. The documented construction
translates the base curve to `SP`, reflects the lower segment, extends linearly
outside LP/HP, and normalizes endpoints to `[0,1]`. All intermediates use float64.

Galaxy implements only the forward generalized-hyperbolic subtype. With
`D=exp(stretch_factor)-1`, the base `T(z)` and derivative are:

- `b=-1`: `T=ln(1+D*z)`, `T'=D/(1+D*z)`;
- `b<0, b!=-1`: `T=(1-(1-b*D*z)^((b+1)/b))/(D*(b+1))`,
  `T'=(1-b*D*z)^(1/b)`;
- `b=0`: `T=1-exp(-D*z)`, `T'=D*exp(-D*z)`;
- `b=1`: `T=1-(1+D*z)^-1`, `T'=D*(1+D*z)^-2`;
- `b>0, b!=1`: `T=1-(1+b*D*z)^(-1/b)`,
  `T'=D*(1+b*D*z)^(-(1+b)/b)`.

Define `T3(x)=T(x-SP)`, `T2(x)=-T(SP-x)`,
`T1(x)=T2'(LP)*(x-LP)+T2(LP)`, and
`T4(x)=T3'(HP)*(x-HP)+T3(HP)`. Select `T1/T2/T3/T4` over the four
intervals split by LP, SP and HP, then normalize every value by
`(value-T1(0))/(T4(1)-T1(0))`. `stretch_factor=0` is exactly identity.
Intermediates are float64. Persisted ranges are stretch factor `[0,20]`, `b`
`[-5,15]`, and `0<=LP<=SP<=HP<=1`. Forward mode only, no blending or inverse
mode, is the bounded Phase 5 scope. The implementation is independently written
from these equations; GPL source is not copied.

## 7. Deferred insertion points

Empirical PSF estimation supplies a qualified native kernel to PSF-RL-001.
Regularized RL would replace, not decorate, PSF-RL-001 after an objective is
selected. Residual registration changes aligned WCS/masks before background work.
Same-band combination operates on compatible aligned-linear packages before
derived arithmetic. Geometry-qualified debanding is native-frame only unless a
separate mosaic-coordinate method is specified. Wavelet denoising is before
display normalization. Masked highlight protection extends tone. None is selected
or authorized by this document.

## 8. References and adaptation record

1. W. H. Richardson, “Bayesian-Based Iterative Method of Image Restoration,”
   *JOSA* 62(1), 55-59 (1972), DOI
   [10.1364/JOSA.62.000055](https://doi.org/10.1364/JOSA.62.000055).
2. L. B. Lucy, “An iterative technique for the rectification of observed
   distributions,” *Astronomical Journal* 79, 745-754 (1974), DOI
   [10.1086/111605](https://doi.org/10.1086/111605).
3. `reproject` project, [Available reprojection algorithms](https://reproject.readthedocs.io/en/latest/explanation/algorithms.html)
   and [Adaptive resampling options](https://reproject.readthedocs.io/en/latest/reference/adaptive_options.html),
   consulted 2026-09-28. These define interpolation/adaptive behavior and the
   flux-per-pixel meaning of `conserve_flux`.
4. D. Payne and M. Cranfield,
   [GeneralizedHyperbolicStretch process documentation](https://www.ghsastro.co.uk/doc/tools/GeneralizedHyperbolicStretch/GeneralizedHyperbolicStretch.html),
   version 3.0.4, consulted 2026-09-28.

Galaxy-specific adaptations are: the explicit IMG-CONTRACT-001 package; MASK-001
semantics; sensitivity-normalized masked RL with invalid latent pixels fixed to
zero; operation-specific derived support; scene/checkpoint identities; and the
presentation support/reference policies. They are not attributed to the cited
sources. Exact dependency versions for reproducibility are recorded in the Phase 0
baseline and later checkpoint manifests.

## 9. Independent verification examples

The machine-readable inputs are
`tests/fixtures/processing_upgrade/numeric_cases.json`.

1. Invalid outlier: replace `1e9` by two other finite extremes; valid normalized,
   mixed, and PSF outputs remain equal within NUM-001 tolerance.
2. Ratio: denominators `0` and `1e-8` are invalid at threshold `1e-6`; `1` and `-2`
   are valid. No epsilon-generated value is exposed as valid.
3. Grid: combining `grid-a` and `grid-b` fails before arithmetic.
4. Sampling: a 0.2-arcsec Gaussian has pixel sigmas `0.8493218` at 0.1 arcsec/pixel
   and `0.4246609` at 0.2 arcsec/pixel, before minimum support-window decisions.
5. Encoding: the specified 1024-level uint16 gradient retains more than 256 levels
   through pipeline TIFF and external TIFF export.
6. Legacy: unaffected normalization/mapping/tone results match the frozen recipe at
   `rtol=atol=1e-6`; every excluded intentional correction is reported separately.

Phase 1 may begin only after normative requirements cite these target sections.
Phase 2 must add the checkpoint wire specification before reuse code. Each later
inventory method must be finalized before its implementation phase.

## Pending presentation bridge amendment (2026-10-05)

REQ-BRIDGE-001..014 and `reprojection_bridge_spec.md` specify a default-on bridge
at the native-input boundary of reprojection. Historical preimplementation state;
see BRIDGE-MEDIAN-001 below for the current native start. MASK-001
and REPROJECT-001 shall distinguish observation validity from estimated
presentation support and transport estimate influence without relabeling missing
measurements as observations. Disabled bridging retains strict existing behavior.

### Load-time workflow clarification (2026-10-06)

REQ-BRIDGE-001..021 supersede the earlier timing shorthand: selected-source
processing automatically prepares the original presentation copy after FITS/mask
ingestion, preserving the raw observational plane for native PSF. The PSF branch
is prepared independently afterward. The low-level observational loader remains
strict. Bridge support/influence contracts must be frozen before implementation
under `compliance_status/reprojection_bridge_plan.md` Phase 1.

## BRIDGE-MEDIAN-001 — native presentation bridge (2026-10-07)

The [Native NaN bridge algorithm](reprojection_bridge_algorithm.md) defines the
constant boundary-median estimator, exact eligibility/profile, observation versus
presentation support, resampling influence, persistence and statistical consumers.
It supersedes the historical harmonic proposal. Native and pipeline/UI integration
are technically verified. BRIDGE-WIRE-002 defines aligned support, positive kernel
influence, statistical exclusion, SUPVER=1 FITS and format-2 checkpoints. User
full-scene presentation acceptance remains recorded in the bridge plan. Existing strict
FITS ingestion and PSF observation semantics remain authoritative.

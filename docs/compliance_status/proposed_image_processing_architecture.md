# Proposed

Galaxy image-processing architecture, 2026-09-28. Companion to [the implementation plan](image_processing_upgrade_implementation_plan.md); compare with [the current architecture](current_image_processing_architecture.md).

**EXISTING** means a current operation retained. **FOUNDATION/FIX** means P00 or essential P0 changes. **NEW** means a planned feature in Phases 3-5. **P2** means a candidate insertion point only, pending user selection. Solid arrows carry data; dashed arrows supply parameters or indicate potential additions. This is not a claim that the new behavior is implemented.

## 1. Native FITS to reusable aligned data

```mermaid
flowchart TD
    F["EXISTING: source FITS files<br/>Originals remain unchanged"]
    L["EXISTING: read image, WCS and metadata<br/>Build DQ / WHT / CTX validity"]
    N["FOUNDATION: complete native image package<br/>Float values + validity + coverage + WCS<br/>Units / domain + source identity + branch"]
    PSF["EXISTING + FIX: optional native PSF branch<br/>Mask-aware RL and correct kernel sampling"]
    PF["Processed native FITS companions<br/>Original branch remains separate"]
    R["EXISTING: reproject original branch"]
    RP["EXISTING: reproject processed branch"]
    A["FOUNDATION: aligned image packages<br/>Each branch retains values, support and WCS"]
    CK["FOUNDATION: validated FITS checkpoint<br/>Producer dependencies + checksums + manifest"]
    B["Continue to linear correction and composition<br/>Separately for each branch"]
    DB["P2: geometry-qualified debanding<br/>Only where detector geometry supports it"]
    EP["P2: empirical PSF estimation<br/>Produces a qualified kernel"]
    RL["P2: regularized RL / deringing<br/>Extends the optional PSF operation"]
    F --> L --> N
    N --> R --> A
    N --> PSF --> PF --> RP --> A
    A --> CK --> B
    DB -. "possible native correction" .-> N
    EP -. "kernel input" .-> PSF
    RL -. "optional method extension" .-> PSF
```

The convergence at aligned packages means a common interface, not mixing of the original and processed branches. Kernel generation feeds PSF processing; it is not another RGB-processing step. Debanding on an already resampled archive mosaic needs its own geometry-qualified specification; merely loading that mosaic does not restore detector coordinates.

## 2. Linear corrections, coverage, normalization and tone

```mermaid
flowchart TD
    A["Aligned image packages from ONE branch<br/>Loaded from a validated checkpoint"]
    BG["NEW: masked sky diagnostics and pedestal correction<br/>Estimate each filter over persisted sky regions<br/>Keep signed residuals and original support"]
    BC["OUTPUT: corrected linear planes<br/>Plus baseline estimates and diagnostic products"]
    D["EXISTING + FIX: derived sums / ratios<br/>Propagate operand validity, units and WCS"]
    CV["NEW: explicit output coverage policy<br/>Legacy available contributors OR common required bands<br/>Optional bounding crop; internal holes stay unsupported"]
    N["NEW: stable normalization / black references<br/>Legacy percentiles, fixed bounds or saved sky region<br/>Background-referenced zero when selected"]
    DP["OUTPUT: display-valued monochrome planes<br/>New single-main-stretch preset uses linear normalization"]
    M["EXISTING: weighted RGB mixing<br/>Carry per-channel support and contributions"]
    RGB["OUTPUT: floating RGB + support"]
    T["NEW: controlled main stretch<br/>Legacy independent channels OR shared-intensity color preservation<br/>Asinh / gamma retained; optional GHS added"]
    SAT["EXISTING: saturation and clipping<br/>Unsupported channels remain zero"]
    O["OUTPUT: final floating display RGB"]
    REG["P2: residual registration<br/>Before matched-region processing; update WCS and masks"]
    ST["P2: robust same-band combination<br/>Before normalization; grouping, ancestry and weights required"]
    DN["P2: wavelet denoising<br/>Linear derived data before strong stretch"]
    MS["P2: masked highlight protection<br/>Extends tone processing"]
    AUTO["NEW: deterministic auto-stretch proposal<br/>Uses persisted reference samples<br/>User applies resolved parameters"]
    A --> BG --> BC --> D --> CV --> N --> DP --> M --> RGB --> T --> SAT --> O
    REG -. "candidate aligned-stage insertion" .-> BG
    ST -. "candidate linear-stage insertion" .-> D
    DN -. "candidate linear-stage insertion" .-> N
    MS -. "candidate tone extension" .-> T
    BC -. "sample diagnostics" .-> AUTO
    AUTO -. "saved parameter choice" .-> T
    BG -. "retain sky-zero reference" .-> N
    N -. "retain chosen black reference" .-> T
```

Background correction has an **off** mode. It runs after current native PSF/reprojection in the initial plan; it does not silently feed signed residuals into RL. The coverage policy controls presentation support without rewriting observational validity.

The black-reference links are essential: subtracting a constant pedestal and then recomputing independent percentiles over the same samples can cancel the subtraction's visual effect. The chosen sky reference must survive both normalization and output tone.

P2 placement arrows identify relevant boundaries, not a fixed ordering among all candidates. If same-band stacking is selected, its subplan must decide background matching before combination, residual registration order, uncertainty propagation and independent-source grouping. Noise-based weights belong to comparable same-band measurements and are not a new default for mixing unrelated filters.

Shared-intensity stretching preserves RGB ratios before gamut/clipping handling. It does not fix an already biased background. Legacy recipes retain their existing normalization/stretch behavior; the single-main-stretch preset is an explicit alternative.

## 3. Output, provenance and reuse

```mermaid
flowchart TD
    RGB["Final floating RGB, per branch"]
    PNG["EXISTING: 8-bit PNG preview"]
    TIFF["EXISTING: 16-bit TIFF render"]
    TH["EXISTING: thumbnail"]
    REC["FOUNDATION: register artifacts by role and branch<br/>Render snapshot, revisions, hashes and provenance"]
    EXP["FIX: export selected branch and format<br/>PNG uses PNG; high-depth TIFF uses TIFF"]
    EXT["External image + export history"]
    DIAG["NEW: correction and support diagnostics<br/>Background regions / baselines / residuals<br/>Coverage and clipping reports"]
    HIST["FOUNDATION: complete processing history<br/>Stage versions, parents and resolved settings"]
    RGB --> PNG --> TH --> REC
    RGB --> TIFF --> REC
    PNG --> REC
    REC --> EXP --> EXT
    DIAG --> REC
    HIST --> REC
```

Across all stages: numerical functions preserve input ownership; image packages retain support and geometry; scene settings participate in current/stale detection; stage diagnostics are distinguishable from observations; failures/cancellation preserve earlier successful renders. Scene rendering and direct aligned-FITS preview share one numerical core.

Reuse rules:

- Tone or post-alignment pedestal changes reuse the unchanged pre-correction aligned checkpoint and recompute downstream results.
- Canvas, source validity, native kernel or native-correction changes invalidate the affected aligned branch.
- Compatibility keys establish whether reuse is appropriate; file checksums establish integrity. Both are required.

## Scope boundaries

Phases 0-2 establish infrastructure and correctness; Phase 3 adds pedestal diagnostics/correction with a functioning black-reference policy; Phase 4 expands coverage/reference policies; Phase 5 adds shared-intensity tone, auto-stretch proposals and GHS; Phase 6 closes out verification. P2 boxes remain unselected until the user chooses them.

Polynomial backgrounds, feathered full-union composites, arbitrary cross-filter histogram matching, LRGB, spline curves, star inpainting, Gaia calibration and drizzle are not implied by this diagram. They remain outside the bounded implementation plan unless separately selected/scoped.

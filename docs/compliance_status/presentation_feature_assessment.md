# Galaxy presentation feature assessment

Date: 2026-09-27. Status: review complete; proposed features are not accepted requirements or implemented behavior.

## Scope and phased review

Source: all 20 proposals in **Compare Galaxy Projects**, conversation `6ab84101-ae1c-83ea-9090-bfdfe63b86ea`, final assistant message `462f14d0-20c6-45c1-8349-d56c5907262f`. Original numbering is retained below. Competitor implementation claims are inspiration, not proof of correctness or suitability.

| Review phase | Exit condition | Disposition |
| --- | --- | --- |
| A: baseline | Recover full list; check requirements and known gaps | Complete |
| B: evidence | Inspect relevant code, tests, saved images and settings | Complete within limitations below |
| C: assessment | Assign every proposal scope, priority, risk and verification | Complete |
| D: closeout | Consolidate findings and propose implementation gates | Complete; actual remediation remains future work |

The working tree already contains substantial changes. This pass adds review documentation only. It does not change application behavior, scene settings or normative requirements.

## Conclusion

Most proposals fit Galaxy's archive-to-presentation purpose, but the ordering needs revision. Reliable validity, coverage and background handling should precede stronger stretching. More aggressive stretch also exposes noise and processing defects; it cannot increase measured signal-to-noise or distinguish an instrumental offset from real diffuse emission.

The list omits **coverage-aware composition**, despite the open cross-instrument coverage entry GAP-COMP-001. That ID is also used by an older closed directory-organization entry; refer to the title as well as the ID until the register is reconciled.

## Current evidence and the reported problems

### Different native scales

`mapping._normalize_plane` performs valid-pixel percentile subtraction/scaling before RGB mixing. This addresses numerical domination by unlike native scales. The current HST/JWST scale regression passes. This remains display normalization, not physical inter-filter calibration: equal units do not imply equal bandpasses or sky distributions.

### Different spatial support

`compose_channels_with_diagnostics` sums weighted normalized planes and ORs their validity masks. It does not compensate for changing contributor sets or feather their edges. A new contributor can therefore cause a brightness/color boundary. Dividing by contributor count alone cannot reconstruct missing wavelengths or make different spectra interchangeable.

The existing source validity fixes should remain intact. Feathering must not turn an uncovered sample into a measurement. A seamless presentation policy and an accurate support map are separate outputs.

### Blue Horsehead sky

Both inspected Horsehead thumbnails show blue observed regions, including the later `render-r7-normalized-tone` image. The later provenance lists only JWST/NIRCam F187N, F212N and F250M, all in `MJy/sr`, mapped respectively to blue, green and red. Coverage is approximately 84.72%, 84.70% and 87.15%. Mixed HST/JWST units cannot explain this particular saved image. The red detector cross is consistent with unequal channel support, not proof of an offset.

The saved recipe applies asinh(4) per plane and subsequently separate channel 1/99-percentile scaling and asinh(4), with unit gains and zero biases. Independent scaling and two nonlinear stages can lift faint signal/noise and alter color relationships. A 0.5th percentile is not an estimate of empty sky; masking uncovered pixels does not neutralize valid sky.

The symptom is confirmed, but this review does not establish whether the blue signal is instrumental background, genuine diffuse emission, differing sampled distributions, or a mixture. No original-FITS background fit was performed. Making selected sky regions dark/neutral is a reasonable presentation goal; automatically suppressing all faint blue nebulosity would be unsafe for signal preservation.

User clarification: a high black baseline in one filter is the suspected cause. Treat residual per-filter sky pedestal/black-reference mismatch as the leading diagnostic hypothesis. The recorded black points are F187N (blue) 4.0305, F212N (green) 0.5399 and F250M (red) 0.2060 MJy/sr. Their difference supports inspecting the baseline but does not prove a calibration defect. A strictly constant additive offset cancels under percentile subtraction; the relevant question is whether the selected black quantile lies below the actual sky baseline, or the baseline varies spatially. Compare all filters over the same valid, source-masked sky regions and record median, spread, selected black point and post-normalization residual. Prioritize this simple pedestal diagnosis before polynomial fitting or more elaborate tone algorithms.

Evidence:

- `artifacts/scenes/horsehead-nebula-3426555b.scene.json`
- `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r5-d9ea73112e78/composite_thumbnail.png`
- `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r7-normalized-tone/composite_thumbnail.png`
- The latter render's `provenance.json`.

### Existing features and correctness concerns

- Asinh/gamma, per-plane percentiles, normalization diagnostics and coverage-aware tone already exist. Broader tone control is an extension.
- Union footprint fitting exists in `viewport_framing.py`; GAP-FRAME-001 and GAP-FRAME-002 are closed. Common-coverage cropping is additional behavior.
- Automatic mapping already sorts wavelength hints, then spaces hues by list rank. `_filter_wavelength_hint` also guesses from filter names without instrument context. Authoritative wavelength metadata and wavelength-distance interpolation are distinct improvements.
- `empirical_psf.py` already has a helper and three tests, but source search found no production caller. It uses ordinary median/MAD and does not propagate FITS masks into estimation. This is not an integrated scene workflow.
- RL already exposes `regularization`, but its implementation adds a denominator term and blends the result with observations. This is not evidence of a Tikhonov objective or deringing.
- `build_deconvolved_plane_artifacts` sends `plane.data` to RL without `plane.mask`, attaching the mask afterward. Invalid values can influence valid neighbors through convolution. A diagnostic using a 9x9 array, 3x3 uniform kernel and three iterations changed only the invalid center from 1 to 1e6; surrounding results changed by up to 2.5639. This supports a REQ-FITS-003 compliance concern.
- `_gaussian_kernel_from_fwhm` interprets arcseconds directly on a pixel grid without a source pixel-scale conversion. A units review is needed before extending PSF behavior for mixed resolutions.

## All 20 proposals

P0 = correctness foundation; P1 = next capability; P2 = conditional follow-on; P3 = defer. Effort is relative, not a schedule estimate.

| Original proposal | Recommendation | Applicability, boundaries and acceptance evidence |
| --- | --- | --- |
| 1. Robust background estimation/subtraction | **P1, very high value; medium effort** | Start with off and a robust pedestal estimated from explicitly selected/masked background samples. Add a low-order spatial model only when gradients justify it. Whole-frame median subtraction can remove nebula. Separate source masks from no-coverage masks; retain signed residuals until display mapping. Save model, sample mask and fit diagnostics. Test known pedestal/gradient recovery and injected diffuse-signal preservation. Defer linked-polynomial models across different filters: their real emission need not share a gradient. |
| 2. JWST 1/f row/column debanding | **P2, conditional; medium/high effort** | Useful for demonstrated stripes, not an automatic JWST operation. Detector axes are not generally mosaic axes; I2D products can combine rotated/resampled exposures. Prefer improved archive products; permit a restricted derived correction only when geometry and source-free samples support it. Save correction/residual maps. Test rotated stripes, real filaments, no-stripe controls and insufficient samples. Horsehead has linear texture, but its physical origin was not established. |
| 3. Generalized Hyperbolic Stretch | **P1 after background/coverage; medium effort** | Good additional global control of faint structure versus cores. Retain asinh; universal superiority is unproven. Specify equations, parameter bounds and clipping. Verify monotonicity, endpoints, limiting cases, finite output and highlight retention. Use one intentional main stretch rather than blindly adding another nonlinear stage. |
| 4. Deterministic STF-style auto-stretch | **P1; medium effort** | Good initial parameter proposal if statistics use valid background samples and expose confidence/failure. Whole-image median and 1.4826*MAD are not necessarily sky/noise estimates in a nebula-filled frame. Persist calculated parameters and allow overrides. Test zero MAD, empty masks, object-filled fields, outliers, repeatability and padding invariance. Define whether crop changes recompute or retain the reference. |
| 5. NaN-aware processing | **P0; medium effort** | Adopt missing-data semantics throughout, not necessarily a NaN-only storage rewrite. Values plus explicit footprints are valid architecture. Audit derived combinations/ratios, PSF processing, background statistics and exports. Changing a masked stored value must not affect valid output. Test mask round trips and neighborhood operations. NaN alone does not represent coverage depth or every validity reason. |
| 6. Automatic valid-footprint crop | **P1 with coverage policy; medium effort** | Preserve exact canvas and current union fitting. Add named intersection policies for contributing channels or required bands. Define holes, disconnected support, empty intersections and margin direction. An intersection's bounding box need not be fully supported. Preview lost area and preserve WCS/stale-render rules. Test internal gaps and unequal support; cropping cannot repair every detector hole. |
| 7. Empirical PSF estimation | **P2; medium/high effort** | Integrate/qualify the existing helper. Require unsaturated isolated stars, local background, subpixel centering, masks, minimum usable count and spatial adequacy. A single PSF may not represent a mosaic. Save kernel FITS, selected/rejected stars, sampling and source identity. Test sparse stars, saturation, ellipticity and known kernels. Fail explicitly rather than inventing a fallback kernel. |
| 8. Regularized RL and deringing | **P2 after correctness; high effort** | Fits the optional derived branch. Fix invalid-pixel influence and kernel units first. Specify a real objective/update rule; do not relabel the current blend. Define treatment of signed background residuals and boundaries. Measure ringing, noise growth, shape/flux error and stopping behavior. Retain original comparison. This does not solve background offsets or footprint changes. |
| 9. Residual registration after WCS | **P2, measurement first; high effort** | Begin with diagnostics and bounded translation. Optical/infrared morphology differs; phase correlation can align unrelated structures. Require common stars or justified common features and confidence checks. Apply transformations consistently to data, masks and uncertainties; record correction alongside original WCS. Test known shifts and ambiguous morphology. Defer affine fitting until measured errors justify it. |
| 10. Same-filter sigma-clipped combination | **P2 when independent repeat products are selected; high effort** | Combine linear compatible measurements before display normalization. Group by mission/instrument/bandpass, units and resolution, not bare filter name. Avoid counting a mosaic and its source exposures as independent. Define one/two-sample behavior; two samples do not identify which is an outlier. Test rejection, masks, weights, overlapping ancestry and boundaries. Cross-observation mosaics remain a separately scoped proposal in current requirements. |
| 11. Wavelength-driven mapping | **P1 metadata correctness; P2 optional spacing; small/medium effort** | Existing rank-based mapping should remain named and reproducible. Use mission/instrument-qualified effective/pivot wavelength metadata with units and provenance. Offer linear/log wavelength spacing as distinct policies. Repeated measurements of a band must not change hues simply by adding list entries. Test mixed optical/NIR/MIR bands, unknown filters and duplicates. Label false color. This does not correct a blue background. |
| 12. Monotonic spline curves | **P3; medium effort** | Useful final refinement after basic presentation control. Persist ordered bounded control points and interpolation/endpoints; test monotonicity and no overshoot. Shared/luminance curves reduce opportunities for color drift. Additional channel curves do not fix foundational background or coverage errors. |
| 13. Masked stretch/highlight protection | **P2/P3 after GHS evaluation; high effort** | Consider only if global controls still lose cores. Persist soft masks; define transitions and coverage behavior. Test halos, star profiles, diffuse detail and local ordering. Require an A/B benefit beyond global controls before adding spatially varying processing. |
| 14. A trous wavelet denoising | **P2 conditional; medium/high effort** | Optional linear derived branch before strong stretch. Needs source/coverage handling and awareness of correlated resampling noise. Test injected filaments, compact sources, noise-only images and removed-detail residuals. Useful presentation control, not recovered measured depth. Promote on evidence rather than default beautification. |
| 15. LRGB/luminance fusion | **P3; high effort** | Explicit creative mapping. High-resolution optical morphology is not necessarily valid infrared morphology. Requires registration and PSF compatibility. Record luminance source; test halos, color ratios and missing coverage. Distinct from applying a common intensity stretch to the existing RGB, which is a narrower, higher-priority addition. |
| 16. Noise-based weighting | **P2 for same-band repeats; defer automatic cross-filter weighting** | Variance weighting is meaningful for comparable measurements after unit/scale conversion. Whole-frame MAD includes structure; WHT is not automatically inverse variance. Weighting unlike filters by noise changes false-color intent and may suppress narrowband signal. Test unbiased recovery and propagated weight scales. Keep cross-band artistic weights explicit. |
| 17. Star separation/inpainting | **P3, outside near-term roadmap; high effort** | Inpainting synthesizes values beneath stars and changes morphology. Only an explicitly named artistic branch could justify it later, with reconstructed-pixel labeling and original comparison. Does not solve current defects. |
| 18. SCNR/green removal | **Exclude from generic pipeline** | No general justification for suppressing green in arbitrary infrared false color. Analogous blue suppression would conceal the Horsehead symptom. Reconsider only for separately specified palette workflows. |
| 19. Gaia spectrophotometric calibration | **Exclude from current scope** | Visible stellar calibration does not define natural RGB for arbitrary JWST infrared filters. A future calibrated broadband optical mode would require a separate photometric purpose/model and validation. |
| 20. Drizzle reconstruction | **Exclude unless scope changes** | Prefer calibrated combined archive products. Exposure reconstruction requires detector sampling, weights, rejection and alignment policies beyond current presentation scope. Distinct from existing WCS reprojection. |

## Missing proposals that directly address the observed issues

**Coverage-aware composition: P0 specification, P1 implementation.** Separate repeat measurements within a band from mixing distinct bands. Normalized weights can prevent equivalent repeat coverage from becoming brighter solely due to contributor count. Missing distinct wavelengths need an explicit common-support crop, incomplete-color indication, or optional feathered presentation transition. Feathering cannot restore missing spectra. Preserve per-channel support and contributor maps.

**Color-preserving main stretch: P1.** After background and band-scale decisions, offer a common intensity-derived multiplier. For positive intensity L, multiplying all RGB values by T(L)/L preserves pre-clipping ratios. Applying the same nonlinear function separately to R, G and B does not generally preserve those ratios. Specify zeros, negative inputs, gamut/clipping and incomplete coverage. This limits added color drift but does not neutralize an already blue input background.

**Stable normalization reference: P1.** Full-frame percentiles change with crop and support. Propose explicit fixed sky regions, full-source reference or fixed numeric bounds. Persist the choice and preserve legacy scenes. Avoid automatic histogram matching of unlike filters: their emission distributions can be physically different.

**Background and clipping diagnostics: P1.** Report sample mask, background/noise estimates and confidence, black/white values, clipped fractions, contributions and coverage; provide correction-map/before-after inspection. Report unknown background when insufficient uncontaminated sky is available. This gives a testable path to dark neutral selected sky without silently deleting faint structure.

## Proposed implementation phases

Each phase begins with accepted atomic requirements, followed by implementation, tests and coverage-matrix updates. These proposals do not themselves authorize implementation.

1. **Correctness baseline:** audit validity through PSF/derived planes, review kernel units, specify coverage behavior, and pin Horsehead plus mixed HST/JWST acceptance fixtures. Exit: masked stored values cannot influence valid outputs; missing-channel behavior is explicit; original checksums are unchanged.
2. **Background and normalization:** masked pedestal first, optional low-order model next, stable statistics references and common-support policies. Exit: synthetic background recovery and diffuse-source preservation pass, underconstrained fits fail visibly, settings/masks survive save/reopen. Agree on Horsehead background samples before measuring neutrality.
3. **Depth presentation:** common-intensity stretch and deterministic auto-parameter proposal, then GHS where A/B evaluation demonstrates benefit. Exit: finite monotonic transforms, controlled clipping, preserved pre-clipping ratios in the preserving mode, reproducible results, quantified noise and retained faint features. Default changes require explicit requirements and compatibility policy.
4. **Measured artifact correction:** conditionally add debanding, residual registration and same-band combination; qualify empirical PSF/RL after correctness fixes. Exit: affected-fixture diagnostics improve and no-defect controls remain intact; masks, geometry and uncertainty provenance track transformations.
5. **Compliance closeout:** every accepted requirement maps to implementation/tests; run offline suite and real-scene/UI preview-save-reopen-compose-only acceptance. Close all intermediary findings with evidence or explicit durable disposition. Deferred features remain deferred, never labeled implemented. Splines, masked stretch, denoising and LRGB require a demonstrated need before further scope acceptance.

Candidate test bounds to finalize during requirements drafting: exact zero outside support; masked-value perturbation invariance to a stated float tolerance; pedestal error <= 0.1 input-noise sigma on a well-conditioned synthetic fixture; <= 1% integrated error in a protected synthetic diffuse source; positive supported RGB ratio relative error <= 1e-5 before clipping. These are proposed fixture criteria, not demonstrated real-image accuracy. Real-scene acceptance needs agreed regions and tolerances, not attractiveness alone.

## Final review dispositions and validation

| Finding | Disposition |
| --- | --- |
| Cross-instrument boundaries | Retain open GAP-COMP-001, cross-instrument title; specify coverage-aware composition next |
| Blue valid Horsehead sky | Symptom confirmed; physical cause unresolved; prioritize samples/background and color diagnostics |
| PSF mask influence | Record compliance concern against REQ-FITS-003 for remediation before PSF expansion |
| Gaussian angular/pixel units | Record code-review concern; require sampling specification and regression |
| Empirical helper | Partial code exists; integration/qualification remains proposed |
| Normalization and union fitting | Preserve completed work; it does not imply broader background/color policies exist |
| All 20 proposals | Fully dispositioned above; none silently promoted to requirements |

Verification: `.venv/Scripts/python.exe -m pytest tests/test_mapping_tone.py tests/test_fitsio.py tests/test_psf.py tests/test_empirical_psf.py -q -p no:cacheprovider` -> **17 passed**. Existing tests establish a baseline, not compliance for proposals. The RL perturbation diagnostic is investigative evidence, not a committed regression. No fresh astronomical render, full-suite run or original-source background attribution was performed for this documentation-only review.

## References

- [Photutils Background2D](https://photutils.readthedocs.io/en/latest/api/photutils.background.Background2D.html) distinguishes source/bad-pixel masks from coverage masks and supports background/RMS modeling. This supports the separate-mask recommendation.
- [STScI clean_flicker_noise](https://jwst-pipeline.readthedocs.io/en/stable/jwst/clean_flicker_noise/main.html) operates on detector ramp/rate data using scene masks and detector-axis structure. Restrictions on applying row/column correction blindly to mosaics are an inference from that geometry.
- [GHS reference](https://www.ghsastro.co.uk/doc/tools/GeneralizedHyperbolicStretch/GeneralizedHyperbolicStretch.html) describes flexible transforms, a common-factor color mode and clipping choices; stretch family and color policy should be evaluated separately.
- [AstroBurst repository](https://github.com/samuelkriegerbonini-dev/AstroBurst) is an inspiration source from the recovered chat. This review does not certify every competitor implementation or recommend copying code.

Local anchors: `mapping.py`, `tone.py`, `fitsio.py`, `reprojection.py`, `psf.py`, `empirical_psf.py`, `processing_config.py`, `viewport_framing.py`. Normative anchors: REQ-SCOPE-001..004, REQ-FITS-001..004, REQ-NORM-001..008, REQ-WCS-001..016, REQ-PSF-001..009 and REQ-ARCH-001..002.

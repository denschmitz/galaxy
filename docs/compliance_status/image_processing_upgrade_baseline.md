# Image-processing upgrade baseline

Date: 2026-09-28. Phase: 0. Status: complete; no runtime behavior changed.

## Scope and repository state

This baseline starts the execution of
[`image_processing_upgrade_implementation_plan.md`](image_processing_upgrade_implementation_plan.md).
The initial checkout contained substantial user-owned changes across requirements,
runtime modules, tests, examples, and scene artifacts. Those changes were preserved.
The Phase 0 work is documentation and deterministic fixture definition only.

The active implementation still matches the 2026-09-27 architecture baseline in
the material areas inspected. The following differences are verified current facts,
not proposed behavior:

- `FITSPlane.mask` is an optional **invalid** mask; `ReprojectedPlane.footprint`
  is required, but WCS is carried separately by orchestration.
- `CompositionInputs` stores values, metadata, and optional footprints in separate
  dictionaries. `compute_derived_planes` returns values without validity, WCS,
  unit, branch, or parent identity.
- `compose_channels_with_diagnostics` performs derived arithmetic, plane
  normalization, RGB mixing, support aggregation, and diagnostics in one function.
- the canonical scene pipeline passes footprints to composition and tone; the
  direct aligned-FITS preview does not.
- compose-only reuse is selected by the presence of `exported_planes.fits`; there
  is no producer dependency manifest or integrity validation.
- canonical pipeline TIFF files are uint16, but external TIFF export opens the
  registered PNG and saves that decoded 8-bit image as TIFF. The render record also
  does not identify the high-depth artifact by role.
- PSF processing runs before reprojection on a separate branch. The active RL call
  ignores `FITSPlane.mask`, clips signed input to nonnegative values, and interprets
  `common_psf_fwhm_arcsec` as a pixel width.

## Baseline environment and test result

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Result: **250 passed, 1 failed, 1 skipped** in 20.02 seconds. The skipped test is
the opt-in public archive integration test. The pre-existing failure is
`tests/test_ui.py::test_inventory_reports_units_masks_normalization_and_mixed_unit_warning`:
the assertion expects both inventory rows to report `native`, while the current
`ready_card()` fixture resolves a non-native policy. This failure is not attributed
to the infrastructure work and was not bypassed or rewritten.

Runtime used for the baseline:

| Dependency | Version |
| --- | --- |
| Python | 3.12.10 |
| NumPy | 2.2.4 |
| SciPy | 1.15.2 |
| Astropy | 6.1.7 |
| reproject | 0.15.0 |
| astroquery | 0.4.11 |
| Pydantic | 2.11.2 |
| Pillow | 11.1.0 |
| tifffile | 2025.2.18 |

## Frozen real-scene evidence

The following existing files are inspection references only. They must not be
overwritten by upgrade testing.

| Role | Relative path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Horsehead card | `artifacts/scenes/horsehead-nebula-3426555b.scene.json` | 967031 | `967700d56743de62681f7cc21c42fb6e8f4ade376f874c8b51c05889d0e3b9d5` |
| Horsehead aligned stack | `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r7-normalized-tone/exported_planes.fits` | 99466560 | `5b694ec547cdd7a612e07b0329165d89d5c121cc7608f7223123a681481c3b84` |
| Horsehead PNG | `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r7-normalized-tone/composite.png` | 6351426 | `c9e7f4c8020d5f224278aa4a0ceb50bee0757a1bcc10b8ea23519a3a4c096fcd` |
| Horsehead TIFF | `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r7-normalized-tone/composite.tiff` | 24858896 | `c35dd41233a53582eb583a1c0c4293091f110392c537994c84925a537a96f898` |
| Horsehead provenance | `artifacts/scenes/horsehead-nebula-3426555b.assets/render-r7-normalized-tone/provenance.json` | 5662 | `134454f26e31fd6e8a7442864fa2c1f85348ff8ab49955cbe69a2e6358843e35` |
| Pillars card | `artifacts/scenes/Pillars.json` | 39740 | `2e1eb97df2789348327dec955268ff92776081b006a7137962531cf41dc9ab94` |
| Pillars aligned stack | `artifacts/scenes/Pillars.assets/render-r5-0ca41ad81945/exported_planes.fits` | 1200081600 | `deda0b5c4c8bc33a218c3c1dd7ecc5bd2c9651d62c651adbc96b574402f4ef1b` |
| Pillars PNG | `artifacts/scenes/Pillars.assets/render-r5-0ca41ad81945/composite.png` | 15438848 | `9b03e0918ba713f30bd81e25b128c4a084c32065417a2ab34d096cbf605d93a2` |
| Pillars TIFF | `artifacts/scenes/Pillars.assets/render-r5-0ca41ad81945/composite.tiff` | 150000272 | `507cd0fae7b30f5742ee1bf2f038bf6302ca9b4400af7eaff94b5c0623f6106a` |
| Pillars provenance | `artifacts/scenes/Pillars.assets/render-r5-0ca41ad81945/provenance.json` | 15496 | `8e361e3a6df4c6a0a0d01e3204e42aec292fee01354b17805366e8752877d67d` |

## Deterministic synthetic fixtures

`tests/fixtures/processing_upgrade/numeric_cases.json` defines the Phase 0
known-answer input cases. Tests added in later phases must generate arrays from the
listed values rather than depend on network or retained scene artifacts. The cases
cover different scales and units, an invalid bright outlier, finite negative data,
constant and empty-valid fields, partial RGB overlap, an internal hole, mismatched
grid identity, a singular ratio denominator, anisotropic sampling, and a uint16
gradient with 1024 distinct levels.

Legacy compatibility is bounded to behavior not intentionally corrected. The
frozen legacy recipe is:

- percentile plane normalization: black `0`, white `100`, linear, gain `1`;
- RGB mapping: low scale to red, high scale to green, constant plane to blue;
- per-channel output tone: black `0`, white `100`, gamma `1`, unit gain, zero bias,
  saturation `1`;
- unsupported samples remain zero;
- numerical comparison tolerance: `rtol=1e-6`, `atol=1e-6` for float stages and
  exact equality after integer encoding.

Intentional corrections excluded from legacy equality are: required support,
derived support propagation, singular-ratio masking, masked PSF behavior, angular
kernel sampling, checkpoint rejection, direct-preview support, and high-depth
external TIFF selection.

## Initial traceability and carried gaps

| Plan item | Current evidence | Phase owner |
| --- | --- | --- |
| P00-01..05 | Optional/split contracts and bare derived arrays verified | Phase 1 |
| GAP-PSF-MASK-001 | Active RL does not receive the mask | Phase 1 |
| GAP-PSF-SCALE-001 | Arcseconds passed directly to pixel-kernel builder | Phase 1 |
| direct preview support | `_render_aligned_planes` omits loaded footprints | Phase 2 |
| P00-06..07 | No checkpoint producer key or integrity manifest | Phase 2 |
| P00-08..09 | Fixed scene input list and non-stage provenance | Phases 2-3 |
| P00-10 | Separate direct-preview numerical route | Phase 2 |
| P00-11..12 | TIFF export decodes registered PNG; branch defaults original | Phase 2 |
| P00-13 | Legacy defaults are materialized but need frozen-path regression | Phases 1-2 |
| GAP-BG-001 | Real-scene interpretation still unresolved | Phase 3 |
| cross-instrument GAP-COMP-001 | Available-contributor support only | Phase 4 |
| GAP-STORAGE-001 | New checkpoint/diagnostic placement not yet normative | Phase 2 |

No Phase 0 gap is closed by this baseline. Phase 0A definitions live in
[`docs/image_processing_architecture.md`](../image_processing_architecture.md).

## Post-baseline disposition (2026-09-28)

The baseline result above remains the immutable before-state. The UI inventory
failure was traced to a test fixture that intended to exercise native mixed-unit
behavior but inherited the newer percentile scene default. The fixture now selects
native normalization explicitly; no runtime behavior was changed for that repair.

After the completed Phase 1 package, derived-arithmetic, geometry, typed
normalization/RGB and PSF slices, the complete offline suite reports 267 passed and
one opt-in live archive test skipped. The frozen Phase 0 numerical recipe now has a
dedicated known-answer regression at the recorded tolerance.
Current implementation state is tracked in
[`processing_upgrade_coverage.md`](../testing/processing_upgrade_coverage.md); this
section does not retroactively change the recorded Phase 0 counts.

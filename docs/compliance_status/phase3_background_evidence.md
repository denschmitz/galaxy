# Phase 3 Background Evidence

Status: complete on 2026-09-29. Human assessment found the candidate significantly
better; background-region correctness remains undetermined.

## Scope

This record evaluates the bounded Phase 3 pedestal workflow against the existing
Horsehead `render-r7-normalized-tone` aligned planes without modifying the saved
scene or render history. It is diagnostic evidence, not a physical calibration
claim.

## Reproducible input and region

- Scene: `artifacts/scenes/horsehead-nebula-3426555b.scene.json`
- Aligned asset: `planes-19e2eceb-4b90-4405-b105-8cd671978293`
- Branch: `original`
- Historical stack: `render-r7-normalized-tone/exported_planes.fits`
- Pixel region: center `(450, 350)`, size `250 x 250`
- ICRS rectangle center: RA `85.20453191566413` degrees, Dec
  `-2.4722717616473147` degrees
- ICRS rectangle size: `17.039028235083236 x 17.039028235083236` arcseconds
- Common geometrical and valid samples: `62,501` (`100%` valid fraction)
- Exclusion regions: none

The historical stack predates persisted WCS headers. The evidence script therefore
uses the explicit inspection-only legacy adapter with the saved render canvas. The
strict checkpoint loader remains fail-loud for missing WCS.

## Resolved diagnostics

| Plane | Pedestal (MJy/sr) | Robust spread | Retained | Rejected |
| --- | ---: | ---: | ---: | ---: |
| F187N | 10.1112308502 | 0.3265838459 | 61,031 | 1,470 |
| F212N | 1.6341290474 | 0.2748454217 | 60,797 | 1,704 |
| F250M | 0.2318623811 | 0.0096705332 | 58,165 | 4,336 |

The much larger F187N pedestal supports the unequal-filter-baseline hypothesis for
this selected region. It does not establish that all diffuse blue emission is
instrumental background.

## Outputs and interpretation

Evidence is stored at
`artifacts/phase3-background-evidence/horsehead-r7-candidate/`:

- `candidate.png` and `candidate.tiff`: candidate `corrected_zero` render
- `background-regions.png`: inclusion-region overlay
- `background-diagnostics.json`: full resolved diagnostics
- `report.json`: reproducible input/output summary

Visual inspection shows much of the blue sky becoming darker or more neutral, but
parts of the nebula and left field shift strongly toward green/yellow. Human
assessment on 2026-09-29 found the candidate significantly better while reporting
that region correctness could not be determined. GAP-BG-001 therefore remains open
for region validation and physical interpretation; the region is not established
as ground truth for later processing.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\phase3_background_candidate.py `
  --scene artifacts\scenes\horsehead-nebula-3426555b.scene.json `
  --aligned-asset-id planes-19e2eceb-4b90-4405-b105-8cd671978293 `
  --branch original --pixel-center-x 450 --pixel-center-y 350 `
  --pixel-width 250 --pixel-height 250 `
  --output-dir artifacts\phase3-background-evidence\horsehead-r7-candidate
```

## Gate

Phase 3 closed after automated acceptance and human confirmation that the candidate
looks significantly better. The human assessment could not validate the region,
so that limitation remains explicit under GAP-BG-001. Phase 4 may proceed, but it
shall preserve region provenance, permit replacement, and avoid treating this
selection as a confirmed physical-sky reference.

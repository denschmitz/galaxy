# Phase 4 coverage and normalization evidence

Date: 2026-10-02

## Automated validation

Command:

```text
.venv\Scripts\python.exe -m pytest -q --basetemp=temp_verify\pytest_tmp
```

Result: 306 passed, one opt-in live archive test skipped. The two warnings are the
known inability to create `.pytest_cache` through the NTFS junction and do not
change test outcomes.

Focused tests cover legacy union support, accepted union-output/common-tone support,
common required-band output, a missing
channel, internal holes, all disconnected components, empty intersection failure,
padding, crop-invariant tone, cropped celestial WCS, fixed numerical bounds,
region-derived locked references, constant/empty reference rejection, mapping
application, scene persistence, pipeline export, and provenance.

## Real-scene comparison

Generated without changing any scene card:

```text
.venv\Scripts\python.exe scripts\phase4_coverage_candidates.py artifacts\scenes\Pillars.json artifacts\scenes\pillars-of-creation-copy-b1289ae4.scene.json artifacts\scenes\pillars-of-creation-copy-611a684c.scene.json artifacts\scenes\horsehead-nebula-3426555b.scene.json --output artifacts\phase4-coverage
```

| Scene | Union output pixels | Common tone-reference pixels | Common / union | Output pixels excluded |
|---|---:|---:|---:|---:|
| Mixed Pillars | 2,356,011 | 428,810 | 18.20% | 0 |
| HST-only Pillars | 3,293,103 | 3,276,515 | 99.50% | 0 |
| JWST-only Pillars | 2,254,912 | 2,204,296 | 97.76% | 0 |
| Horsehead | 3,740,289 | 3,379,350 | 90.35% | 0 |

The complete machine-readable diagnostics and PNG candidates are under
`artifacts/phase4-coverage`. Horsehead uses the explicit inspection-only fallback
WCS reconstructed from its persisted canvas because its historical aligned stack
predates WCS persistence; the report records this fact. The other three aligned
stacks carry their own celestial WCS.

The accepted `accepted-union-common-tone.png` candidate retains the full union,
calculates each final channel's visual range from common-overlap pixels, and applies
that unchanged transform to partial-support pixels. It does not divide by the number
of contributing planes or bring up partial areas. The user accepted this behavior
on 2026-10-02. Common-only and common-crop candidates remain diagnostic alternatives.

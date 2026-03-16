# Galaxy Design Requirements

## Purpose

This document tracks the initial Galaxy design against the provided requirements. The repository implements the P0 path fully enough to establish a working baseline and adds structured extension points for P1 and P2 features.

## Architecture summary

Galaxy is organized as a staged pipeline:

1. `config`: canonical YAML schema and validation
2. `targeting`: target-name resolution and explicit coordinate parsing
3. `mast`: MAST search filtering, deterministic product selection, and manifest creation
4. `fitsio`: FITS ingestion, WCS extraction, and metadata propagation
5. `reprojection`: output canvas definition and reprojected plane generation
6. `planes`: multi-plane container and export
7. `mapping` and `tone`: RGB channel mixing, derived planes, and presentation stretch controls
8. `export`: PNG/TIFF and aligned multi-plane FITS output
9. `provenance`: reproducibility record including software versions and run inputs
10. `cli` and `ui`: non-interactive pipeline orchestration and preview tuning

## Requirement mapping

### P0 implemented in this baseline

- `REQ-SCOPE-001` to `REQ-SCOPE-003`: source files are cached unmodified; presentation operations are isolated to derived outputs.
- `REQ-TARGET-001` to `REQ-TARGET-004`: implemented in `targeting.py` and provenance serialization.
- `REQ-DATA-001` to `REQ-DATA-006`: implemented in `mast.py` and `cache.py` with deterministic ranking and manifest reporting.
- `REQ-INPUT-001` to `REQ-INPUT-004`: implemented in `fitsio.py`.
- `REQ-WCS-001` to `REQ-WCS-005`: implemented in `reprojection.py`.
- `REQ-PLANE-001` to `REQ-PLANE-003`: implemented in `planes.py`.
- `REQ-MAP-001` to `REQ-MAP-005`: implemented in `mapping.py`.
- `REQ-TONE-001` to `REQ-TONE-005`: implemented in `tone.py`.
- `REQ-CLI-001` to `REQ-CLI-004`: implemented in `cli.py`.
- `REQ-OUT-001` to `REQ-OUT-005`: implemented in `export.py` and `provenance.py`.
- `REQ-REPRO-001` to `REQ-REPRO-004`: canonical YAML config, `reproduce` command, pinned dependencies, examples/tutorial.
- `REQ-PERF-001` to `REQ-PERF-003`: preview downsampling hooks and progress callbacks built into the pipeline.
- `REQ-REL-001` to `REQ-REL-003`: field validation, WCS validation, and continue-on-error support.
- `REQ-TEST-001` and a partial `REQ-TEST-002`: automated unit coverage plus an opt-in integration test scaffold.
- `REQ-DOC-001`, `REQ-DOC-002`, `REQ-LIC-001`, `REQ-LIC-002`: repository docs and license included.

### P1 partially implemented, ready for expansion

- `REQ-PSF-001` to `REQ-PSF-006`: config schema and provenance hooks exist; the default implementation is pass-through and intentionally bounded.
- `REQ-UI-001` to `REQ-UI-006`: Streamlit preview UI loads aligned planes, supports control tuning, and can save/load mapping state. It currently operates on exported aligned plane products rather than orchestrating the full upstream pipeline.

### P2 deferred

- Advanced astrometric refinement
- Empirical PSF fitting
- Local contrast enhancement

## Deterministic product selection rule

When multiple MAST products map to the same observation/filter combination, Galaxy ranks candidates by:

1. pipeline-produced science-like product type (`SCIENCE`, `DRZ`, `DRC`, `I2D`, `CAL`, then others)
2. explicit preference for image-like FITS files
3. newest product version if available
4. stable lexical tiebreaker on product identifier

This rule is documented in code and persisted in the manifest and provenance.

## Risks and follow-up work

- The MAST integration test is opt-in because it depends on live public services and network access.
- Some archives expose mission-specific metadata inconsistently; filters are normalized conservatively to keep the selection rule deterministic.
- Presentation deconvolution remains intentionally conservative in the baseline and should be expanded with mission-aware PSF support in P1.


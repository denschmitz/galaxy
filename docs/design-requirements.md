# Galaxy Design Requirements

## 1. Purpose

This document defines the normative behavioral requirements for Galaxy. These requirements determine system behavior and shall be used as the basis for implementation and verification.

Galaxy shall produce presentation-oriented composite images from public astronomy archive products while preserving provenance and maintaining unmodified cached source data.

## 2. System Scope

### REQ-SCOPE-001 Source Preservation

The system shall cache all downloaded archive products without modification.

### REQ-SCOPE-002 Derived Processing

The system shall perform all processing operations only on derived data products.

### REQ-SCOPE-003 Provenance Recording

The system shall generate a provenance record for every pipeline execution.

### REQ-SCOPE-004 Candidate Persistence

The system shall persist archive discovery results as a candidate manifest file.

## 3. System Architecture

### REQ-ARCH-001 Pipeline Structure

The system shall execute processing as an ordered pipeline consisting of:

1. configuration validation
2. target resolution
3. archive discovery and selection
4. FITS ingestion
5. reprojection
6. plane management
7. mapping and tone processing
8. PSF processing
9. export
10. provenance recording

### REQ-ARCH-002 Stage Isolation

Each pipeline stage shall operate only on inputs produced by prior stages and shall not modify upstream artifacts.

## 4. Target Resolution and Search Geometry

### REQ-TARGET-001 Coordinate Precedence

The system shall resolve target coordinates using the following precedence:

1. decimal coordinates
2. sexagesimal coordinates
3. name resolution

### REQ-TARGET-002 Name Resolution Usage

The system shall perform name resolution only when explicit coordinates are not provided.

### REQ-TARGET-003 Circular Queries

The system shall issue circular region queries directly to the archive.

### REQ-TARGET-004 Box Approximation

The system shall approximate rectangular search regions as circumscribed circles when querying the archive.

### REQ-TARGET-005 Polygon Support

The system shall not perform polygon-based archive queries.

## 5. Archive Discovery and Data Handling

### REQ-DATA-001 Observation Query

The system shall query observations before querying products.

### REQ-DATA-002 Observation Filtering

The system shall filter observations by mission and instrument.

### REQ-DATA-003 Product Retrieval

The system shall retrieve product metadata in batches using observation identifiers.

### REQ-DATA-004 Metadata Enrichment

The system shall propagate observation-level metadata to associated products.

### REQ-DATA-005 Product Filtering

The system shall filter products by detector, filter, product type, and optional observation date range.

### REQ-DATA-006 Candidate Manifest Generation

The system shall produce a candidate manifest containing all filtered candidate products.

### REQ-DATA-007 Metadata Normalization

The system shall normalize mission-specific metadata fields, including filter names, product types, exposure time values, and observation date fields, into canonical internal representations prior to ranking or selection.

### REQ-DATA-008 Total Ordering

The system shall produce a deterministic total ordering of all candidate products regardless of missing or equivalent metadata.

### REQ-DATA-009 Selection-State Consistency

The system shall ensure that candidate selection fields are internally consistent. The final selection state shall reflect application of selection policy and user overrides.

## 6. Deterministic Product Selection

### REQ-SELECT-001 Ranking Rule

The system shall rank candidate products within each observation/filter group using:

1. product type priority (`SCIENCE`, `DRZ`, `DRC`, `I2D`, `CAL`, others)
2. preference for image-like FITS products
3. newest product version
4. stable lexical identifier ordering

### REQ-SELECT-002 Selection Policy

The system shall support selection policies:

- all
- latest per filter
- deepest per filter

### REQ-SELECT-003 Selection Limits

The system shall support:

- maximum observations per filter
- maximum total selected observations

### REQ-SELECT-004 Explicit Overrides

The system shall apply explicit include/exclude filters after ranking.

### REQ-SELECT-005 Selection Persistence

The system shall record final selected candidates in both the candidate manifest and provenance record.

## 7. Reprojection

### REQ-WCS-001 Configured Canvas

The system shall construct the output WCS from configured parameters including center, projection, pixel scale, width, height, and rotation.

### REQ-WCS-002 Reprojection Surface

The system shall reproject all usable input planes onto the configured output canvas.

### REQ-WCS-003 Processing Order

The system shall load all usable FITS planes prior to reprojection.

### REQ-WCS-004 Reprojection Mode Recording

The system shall record reprojection mode in provenance.

### REQ-PERF-004 Memory Estimate Definition

The reprojection memory estimate shall be computed as a deterministic function of:

- output pixel count
- number of planes
- bytes per pixel
- reprojection method

For identical inputs, the same estimate shall be produced.

### REQ-PERF-005 Memory Warning

The system shall emit a warning when estimated memory usage reaches at least 80% of installed system memory.

## 8. FITS Ingestion

### REQ-INPUT-001 FITS Loading

The system shall load FITS data and extract WCS information.

### REQ-INPUT-002 Metadata Fallback

The system shall use PRIMARY header metadata when SCI metadata is unavailable.

## 9. Plane Management

### REQ-PLANE-001 Alignment

The system shall represent aligned data as multi-plane datasets.

### REQ-PLANE-002 Enablement

The system shall support enabling and disabling planes.

## 10. Mapping and Tone

### REQ-MAP-001 Composition

The system shall combine planes into RGB outputs.

### REQ-TONE-001 Tone Processing

The system shall apply tone transformations to derived outputs.

## 11. PSF Processing

### REQ-PSF-001 Optional Processing

The system shall perform PSF processing only when enabled.

### REQ-PSF-002 Kernel Requirement

The system shall fail execution when PSF processing is enabled and no valid kernel is available.

### REQ-PSF-003 Processing Method

The system shall apply Richardson-Lucy deconvolution.

## 12. Export

### REQ-OUT-001 Output Formats

The system shall export images in PNG or TIFF format.

## 13. Provenance

### REQ-REPRO-001 Provenance Content

The system shall record:

- execution source
- selection policy
- selected candidate identifiers
- reprojection parameters
- memory estimate

## 14. Candidate Manifest

### REQ-MAN-001 Manifest Format

The system shall produce a JSON candidate manifest.

### REQ-MAN-002 Required Fields

Each candidate record shall include defined metadata fields including identifiers, observation metadata, and selection state.

### REQ-MAN-003 Manifest Metadata

The manifest shall include generation time, configuration reference, selection policy, and selection inputs.

## 15. CLI

### REQ-CLI-001 Discovery Command

The system shall support a discovery command that outputs a candidate manifest.

### REQ-CLI-002 Execution Command

The system shall support execution using a configuration and optional selection manifest.

### REQ-CLI-003 Execution Modes

The system shall support full, download-only, reprojection-only, and compose-only modes.

## 16. UI

### REQ-UI-001 Discovery Mode

The system shall support archive discovery and candidate selection.

### REQ-UI-002 Preview Mode

The system shall support preview of aligned planes.

### REQ-UI-003 Selection Controls

The system shall allow per-candidate selection.

## 17. Discovery Cache

### REQ-CACHE-001 Cache Persistence

The system shall persist discovery results to disk.

### REQ-CACHE-002 Cache Reuse

The system shall reuse persisted discovery results when query inputs are unchanged.

### REQ-CACHE-003 Cache Expiration

The system shall treat persisted discovery results older than 6 months as stale unless explicitly reused.

### REQ-CACHE-004 Forced Refresh

The system shall allow users to force a new archive query.

## 18. Logging

### REQ-LOG-001 Discovery Logging

The system shall log archive query progress and counts.

### REQ-LOG-002 Download Logging

The system shall log download progress and failures.

### REQ-LOG-003 Reprojection Logging

The system shall log reprojection parameters and memory warnings.

## 19. Testing

### REQ-TEST-001 Unit Coverage

The system shall provide automated tests for core pipeline logic.

### REQ-TEST-002 Offline Testability

Core behaviors shall be testable without network access.

## 20. Known Limitations

The system does not currently support:

- polygon-based archive queries
- advanced astrometric refinement
- empirical PSF fitting
- robust geometric output derivation for mixed footprints

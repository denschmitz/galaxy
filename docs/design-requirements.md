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

1. Galaxy project file validation
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

### REQ-ARCH-003 Tooling Compatibility

The system shall support debugger and launcher environments in which module-level argument forwarding is unreliable, without changing UI mode semantics.

## 4. Galaxy Project File Format

### REQ-PROJ-001 Project File Artifact

The system shall define a normative Galaxy project file format represented in YAML.

### REQ-PROJ-002 Project File Purpose

The Galaxy project file shall represent the persisted user-editable description of a Galaxy work item, including search inputs, selection constraints, canvas settings, mapping settings, tone settings, optional processing settings, and saved presentation-state adjustments.

### REQ-PROJ-003 Project File Role Separation

The Galaxy project file shall be distinct from:

- cached source archive products
- candidate manifest artifacts
- provenance artifacts
- exported composite image artifacts

### REQ-PROJ-004 Project File Loadability

The system shall be able to execute discovery, reprojection, and composition from a Galaxy project file without requiring any other user-authored configuration artifact.

### REQ-PROJ-005 Project File Saveability

The system shall be able to write a Galaxy project file reflecting the current user-selected settings from the UI or CLI workflow.

### REQ-PROJ-006 Stable Round Trip

For a valid Galaxy project file, loading the file and saving it without user changes shall preserve semantic meaning and shall not lose defined fields.

### REQ-PROJ-007 Unknown Field Handling

The system shall reject unknown Galaxy project file fields according to a documented validation policy.

### REQ-PROJ-008 Required Top-Level Structure

The Galaxy project file shall support the following top-level sections:

- target
- search
- canvas
- planes
- mapping
- tone
- psf
- execution

### REQ-PROJ-009 Required Minimum Content

A valid Galaxy project file shall contain sufficient information to define either:

- a search-driven scene definition including a target and search constraints
- a pinned scene definition including explicit source-product identities

A valid Galaxy project file shall also define:

- a valid output canvas
- a valid automatic mapping strategy or explicit mapping definition

### REQ-PROJ-010 Validation

The system shall validate Galaxy project files before execution and shall report schema or value errors with field-specific diagnostics.

### REQ-PROJ-011 Search Constraints

The search section shall support optional constraints including:

- missions
- instruments
- detectors
- filters
- product types
- observation date range
- selection policy
- observation limits

### REQ-PROJ-012 Exact Product Selection Support

The Galaxy project file format shall support optional explicit source-product identifiers to allow exact archive product reuse without rediscovery. When explicit source-product identifiers are present, they shall take precedence over rediscovery-based source-product selection constraints.

### REQ-PROJ-013 Canvas Definition

The canvas section shall define the output sky projection and raster geometry including center, projection, pixel scale, width, height, and rotation.

### REQ-PROJ-014 Saved View State

The Galaxy project file format shall support persistence of user-adjusted output view parameters that affect composition framing.

### REQ-PROJ-015 Plane Activation

The planes section shall support enabling and disabling source planes and filters for downstream composition.

### REQ-PROJ-016 Mapping Strategy

The mapping section shall support both:

- automatic mapping strategies
- explicit per-plane RGB contribution definitions

### REQ-PROJ-017 Explicit Plane Mapping

When explicit per-plane mapping is present, the Galaxy project file shall be able to persist user-defined RGB assignments and labels for each mapped plane.

### REQ-PROJ-018 Mapping Precedence

When explicit per-plane mapping is present, it shall take precedence over automatic mapping strategy fields.

### REQ-PROJ-019 Tone Persistence

The tone section shall support persistence of user-adjusted presentation parameters including stretch, clipping, channel gain, channel bias, and saturation.

### REQ-PROJ-020 Tone Scope

Tone parameters persisted in the Galaxy project file shall apply per output channel. Per-plane tone persistence is not required unless explicitly introduced by a future schema revision.

### REQ-PROJ-021 Execution Policy Separation

The execution section shall contain runtime policy settings and shall not alter the semantic meaning of the intended source scene or visual composition.

### REQ-PROJ-022 UI Save Semantics

When the user saves a project from the UI, the system shall write a Galaxy project file containing the current persisted scene definition and all user-adjustable settings designated as saveable.

### REQ-PROJ-023 Saveable Adjustments

Saveable Galaxy project file settings shall include, at minimum:

- canvas framing parameters
- enabled and disabled planes
- explicit plane-mapping assignments
- tone and color-adjustment parameters
- PSF enablement state

### REQ-PROJ-024 Non-Saveable Runtime State

Transient UI state not intended to affect reproducible output shall not be required to persist in the Galaxy project file.

### REQ-PROJ-025 Search-Driven and Pinned Modes

The Galaxy project file format shall support both:

- search-driven scene definitions based on archive constraints
- pinned scene definitions based on explicit source-product identities

### REQ-PROJ-026 Project File Noncompliance Logging

The system shall log detected noncompliance with the current Galaxy project file format, including unknown fields, invalid values, unsupported section combinations, deprecated structures, and unsupported format revisions, with field-specific diagnostics.

## 5. Target Resolution and Search Geometry

### REQ-TARGET-001 Coordinate Precedence

The system shall resolve target coordinates from the target section of the Galaxy project file using the following precedence:

1. decimal coordinates
2. sexagesimal coordinates
3. name resolution

### REQ-TARGET-002 Name Resolution Usage

The system shall perform name resolution from the target section only when explicit coordinates are not provided in the Galaxy project file.

### REQ-TARGET-003 Circular Queries

The system shall issue circular region queries directly to the archive.

### REQ-TARGET-004 Box Approximation

The system shall approximate rectangular search regions as circumscribed circles when querying the archive.

### REQ-TARGET-005 Polygon Support

The system shall not perform polygon-based archive queries.

## 6. Archive Discovery and Data Handling

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

### REQ-DISC-001 Multiple Discovery Entry Points

The system shall support multiple user discovery entry points for finding candidate JWST scenes.

### REQ-DISC-002 Discovery Role Separation

The system shall distinguish scene opportunity discovery from archive product discovery.

### REQ-DISC-003 External Tracker Authority Boundary

The system shall treat external tracker records as discovery hints and shall not treat them as authoritative archive product manifests.

### REQ-DISC-004 MAST Product Authority

The system shall use MAST as the authoritative source for archive product metadata, downloadable product identities, and candidate manifest records.

### REQ-DISC-005 Discovery Hint Source Provenance

The system shall record the source URL, retrieval time, and extracted metadata for imported external discovery hints.

### REQ-DISC-006 Discovery Hint Conversion

The system shall convert imported external discovery hints into Galaxy project search inputs or user-facing search suggestions before archive product discovery.

### REQ-DISC-007 External Discovery Failure Isolation

The system shall continue to support normal MAST discovery when an external discovery source fails.

### REQ-DISC-008 Latest JWST Release Tracker Source

The system shall support the Yuval Harpaz latest JWST release tracker at `https://yuval-harpaz.github.io/astro/jwst_latest_release.html` as an external discovery hint source.

### REQ-DISC-009 Discovery Hint Alignment

The system shall support an optional discovery-hint alignment rotation value expressed in degrees.

### REQ-DISC-010 Alignment Rotation Bounds

The system shall accept discovery-hint alignment rotation values from 0 degrees through 360 degrees inclusive.

### REQ-DISC-011 Alignment Default

The system shall default omitted discovery-hint alignment rotation values to 0 degrees.

## 7. Deterministic Product Selection

### REQ-SELECT-001 Ranking Rule

The system shall rank candidate products within each observation/filter group using:

1. product type priority (`SCIENCE`, `DRZ`, `DRC`, `I2D`, `CAL`, others)
2. preference for image-like FITS products
3. newest product version
4. stable lexical identifier ordering

### REQ-SELECT-002 Selection Policy

The system shall support selection policies defined by Galaxy project file search constraints and optional user overrides:

- all
- latest per filter
- deepest per filter

### REQ-SELECT-003 Selection Limits

The system shall support project-file-defined and user-overridden selection limits including:

- maximum observations per filter
- maximum total selected observations

### REQ-SELECT-004 Explicit Overrides

The system shall apply explicit include and exclude selection overrides after ranking, using project-file-defined search constraints and optional user overrides.

### REQ-SELECT-005 Selection Persistence

The system shall record final selected candidates in both the candidate manifest and provenance record.

## 8. Reprojection

### REQ-WCS-001 Configured Canvas

The system shall construct the output WCS from the canvas section of the Galaxy project file, including center, projection, pixel scale, width, height, and rotation.

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

## 9. FITS Ingestion

### REQ-INPUT-001 FITS Loading

The system shall load FITS data and extract WCS information.

### REQ-INPUT-002 Metadata Fallback

The system shall use PRIMARY header metadata when SCI metadata is unavailable.

## 10. Plane Management

### REQ-PLANE-001 Alignment

The system shall represent aligned data as multi-plane datasets.

### REQ-PLANE-002 Enablement

The system shall support enabling and disabling planes.

### REQ-PLANE-003 Reprojected Plane Format

The system shall persist reprojected plane artifacts in FITS format.

### REQ-PLANE-004 Floating Pixel Support

The reprojected plane artifact format shall support at least 32-bit floating-point pixel values without display-oriented quantization.

### REQ-PLANE-005 WCS and Source Metadata

Each persisted reprojected plane artifact shall include sufficient metadata to reconstruct the output-canvas sky alignment and the originating source-product identity.

### REQ-PLANE-006 Multi-Plane Export Format

When the system exports an aligned plane set as a stacked artifact, it shall use a FITS-based representation.

## 11. Mapping and Tone

### REQ-MAP-001 Composition

The system shall combine planes into RGB outputs using Galaxy project file mapping settings.

### REQ-TONE-001 Tone Processing

The system shall apply tone transformations using Galaxy project file tone settings.

## 12. PSF Processing

### REQ-PSF-001 Dual Artifact Paths

The system shall preserve both the original image path and the PSF-processed image path as distinct artifact branches.

### REQ-PSF-002 Optional Processing

The system shall perform PSF processing only when enabled for a plane or artifact branch.

### REQ-PSF-003 Kernel Requirement

The system shall fail execution for the PSF-processed branch when PSF processing is enabled and no valid kernel is available for the corresponding source image.

### REQ-PSF-004 Native-Frame Processing

The system shall apply instrument-specific PSF processing to the image artifact in the image frame for which the kernel is defined, prior to reprojection onto a shared canvas.

### REQ-PSF-005 Cached PSF Artifact

When PSF processing is enabled, the system shall read the source FITS image and its kernel, generate a PSF-processed companion image, and store that companion artifact alongside the original cached source image.

### REQ-PSF-006 Parallel Reprojection Branches

The system shall carry both original-image artifacts and PSF-processed artifacts through reprojection as separate branches.

### REQ-PSF-007 Branch-Selective Composition

The system shall allow downstream composition to select either the original branch or the PSF-processed branch by artifact identity.

### REQ-PSF-008 Dual Export Outputs

When both original and PSF-processed branches are present, the system shall generate PNG and TIFF outputs for both branches.

### REQ-PSF-009 Processing Method

The system shall apply Richardson-Lucy deconvolution for the PSF-processed branch.

## 13. Export

### REQ-OUT-001 Output Formats

The system shall export presentation composites in PNG or TIFF format.

### REQ-OUT-002 Reprojected Footprint Overlay

The system shall generate a visualization artifact with the same pixel dimensions as the configured output canvas showing the projected footprints of the selected source FITS images.

### REQ-OUT-003 Reprojected Footprint Overlay Appearance

In the footprint overlay artifact, source-image boundaries shall be rendered as white outlines and all non-boundary pixels shall be rendered as black.

### REQ-OUT-004 Reprojected Footprint Overlay Purpose

The footprint overlay artifact shall be intended for human inspection of how the selected archive assets map onto the configured output rectangle.

## 14. Provenance

### REQ-REPRO-001 Provenance Content

The system shall record:

- execution source
- selection policy
- selected candidate identifiers
- reprojection parameters
- memory estimate

## 15. Candidate Manifest

### REQ-MAN-001 Manifest Format

The system shall produce a JSON candidate manifest.

### REQ-MAN-002 Required Fields

Each candidate record shall include defined metadata fields including identifiers, observation metadata, and selection state.

### REQ-MAN-003 Manifest Metadata

The manifest shall include generation time, Galaxy project file reference, selection policy, and selection inputs.

## 16. CLI

### REQ-CLI-001 Discovery Command

The system shall support a discovery command that outputs a candidate manifest.

### REQ-CLI-002 Execution Command

The system shall support execution using a Galaxy project file and optional selection manifest.

### REQ-CLI-003 Execution Modes

The system shall support full, download-only, reprojection-only, and compose-only modes.

## 17. UI

### REQ-UI-001 Discovery Mode

The system shall support archive discovery and candidate selection.

### REQ-UI-002 Preview Mode

The system shall support preview of aligned planes.

### REQ-UI-003 Preview Branch Selection

When both original and PSF-processed aligned-plane artifacts are available for the same workdir, the preview UI shall allow the user to select which branch to preview.

### REQ-UI-004 Selection Controls

The system shall allow per-candidate selection.

### REQ-UI-005 Input Resolution

The UI entrypoint shall accept its initial input path from any of the following:

- a launch-time argument
- an environment-provided override
- automatic workspace artifact discovery when neither of the above is available

The resolved input may reference:

- a Galaxy project file
- a candidate manifest JSON
- a multi-plane FITS file
- a workdir that resolves to one of those artifacts

The Galaxy project file shall be a first-class UI input type for both discovery-oriented workflows and saveable project-state editing.

When automatic workspace artifact discovery is used, the UI shall prefer original aligned-plane artifacts over PSF-processed aligned-plane artifacts, discovery manifests, and Galaxy project files.

## 18. Discovery Cache

### REQ-CACHE-001 Cache Persistence

The system shall persist discovery results to disk.

### REQ-CACHE-002 Cache Reuse

The system shall reuse persisted discovery results when query inputs are unchanged.

### REQ-CACHE-003 Cache Expiration

The system shall treat persisted discovery results older than 6 months as stale unless explicitly reused.

### REQ-CACHE-004 Forced Refresh

The system shall allow users to force a new archive query.

## 19. Logging

### REQ-LOG-001 Discovery Logging

The system shall log archive query progress and counts.

### REQ-LOG-002 Download Logging

The system shall log download progress and failures.

### REQ-LOG-003 Reprojection Logging

The system shall log reprojection parameters and memory warnings.

### REQ-LOG-004 Project File Validation Logging

The system shall log Galaxy project file validation failures with field-specific diagnostics sufficient to identify the noncompliant field or section.

### REQ-LOG-005 Project File Format Noncompliance Logging

The system shall log any detected noncompliance with the current Galaxy project file format, including unknown fields, invalid values, unsupported combinations, deprecated structures, and unsupported format revisions.

### REQ-LOG-006 Logging Severity Scheme

The system shall implement a system-wide logging severity scheme with at least the following levels:

- ERROR
- WARNING
- INFO
- DEBUG

### REQ-LOG-007 Severity Semantics

The system shall use logging severities consistently according to the following intent:

- ERROR for failures, noncompliance, or conditions that prevent successful completion of a required operation
- WARNING for abnormal or degraded conditions that do not prevent continued operation
- INFO for routine operational milestones, progress events, and major state transitions
- DEBUG for detailed diagnostic information intended primarily for troubleshooting and development

### REQ-LOG-008 Console Logging Sink

The system shall emit logs to the console during execution.

### REQ-LOG-009 File Logging Sink

The system shall persist logs to a file during execution.

### REQ-LOG-010 Dual-Sink Consistency

The system shall use the same system-wide logging severity scheme for both console and file logging sinks.

### REQ-LOG-011 Log Record Content

Each log record shall include, at minimum:

- a timestamp
- a severity level
- a message

### REQ-LOG-012 Debug Visibility Control

The system shall support configuration of whether DEBUG-level log records are emitted to console, file, or both.

## 20. Testing

### REQ-TEST-001 Unit Coverage

The system shall provide automated tests for core pipeline logic.

### REQ-TEST-002 Offline Testability

Core behaviors shall be testable without network access.

## 21. Known Limitations

The system does not currently support:

- polygon-based archive queries
- advanced astrometric refinement
- empirical PSF fitting
- robust geometric output derivation for mixed footprints
- physically exact PSF transport through reprojection for a single-kernel post-reprojection workflow

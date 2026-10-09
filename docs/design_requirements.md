# Galaxy Design Requirements

## 1. Purpose and document conventions

Galaxy produces presentation-oriented composite images from public astronomy archive products while preserving source data and provenance. This document is the normative source of truth. “Shall” defines a required behavior; headings, rationale, and examples do not create additional requirements.

The [Artifact storage specification](artifact_storage_spec.md) is the normative
filesystem layout and naming contract referenced by the storage requirements in
this document. The [Scene card schema](scene_card_schema.md) remains the normative
JSON structure and reference contract.

Requirements are organized by engineering concern. Existing requirement identifiers are retained for traceability. New screen requirements describe the target design, not a claim of implemented support.

Supporting specifications:

- [User flows](user_flows.md): five screens, transitions, and observable states (UF-01 through UF-05).
- [Scene card storage schema](scene_card_schema.md): normative scene-card format and persistence rules.
- [Selection guidance specification](selection_guidance_spec.md): candidate identity, selection modes, grouping, summaries, and concise explanation format.
- [Selected-footprint viewport specification](viewport_framing_spec.md): FITS footprint geometry, fitted-canvas derivation, and warning thresholds.
- [Image-processing architecture](image_processing_architecture.md): numerical image contracts, validity and coverage semantics, stage boundaries, and selected algorithm definitions.
- [UI acceptance coverage](testing/ui_scene_coverage.md): planned acceptance scenarios and implementation gaps.
- [Image-processing upgrade coverage](testing/processing_upgrade_coverage.md): P00 proposal and later processing-method traceability.
- [Known gaps](compliance_status/known_gaps.md): unresolved implementation and specification work.

Requirements take precedence over flows; the storage schema supplies field-level definitions referenced by REQ-CARD-001. Supporting documents must be updated together when a contract changes.

### Behavioral definitions

| Term | Meaning |
| --- | --- |
| Discovery hint | A source-attributed suggestion of a target or sky region; archive availability is unverified. |
| Scene | Target or region plus data selection, frame, and composition settings. |
| Scene card | The canonical JSON project document, containing scene inputs, settings, selected source identities, and artifact records; optional associated files hold binary assets. |
| Bundled example | A source-controlled scene-card JSON template stored under the project `examples/` directory. It is never an editable user scene. |
| User copy | The materialized copy of a bundled example in the effective scene directory. The user copy and its associated asset root are ordinary user-owned scene data. |
| Observation group | Products associated with one authoritative archive observation identity. Separate visits and identities remain separate; a shared target name does not merge them. |
| Candidate product | An archive product eligible for user selection under discovery constraints. |
| Draft | A structurally valid scene card with optional unfinished sections; specific actions are enabled only when their readiness checks pass. |
| Render-ready | A derived condition indicating resolved geometry, selected product identities, and complete valid render settings; file availability is checked separately. |
| Preview | A successful Galaxy render associated with a scene content revision and branch. |
| Crop frame | The sky footprint of the output canvas, rather than a crop applied only to the displayed thumbnail. |

## 2. Externally driven requirements and scope

The user workflow begins with discovery, permits iterative refinement and rendering, and preserves a reusable scene card independently of image export. MAST supplies authoritative archive metadata. External release trackers supply discovery hints. These drivers motivate the interface and behavioral requirements below.

### Source preservation and reproducibility

#### REQ-SCOPE-001 Source Preservation

The system shall cache all downloaded archive products without modification.

#### REQ-SCOPE-002 Derived Processing

The system shall perform all processing operations only on derived data products.

#### REQ-SCOPE-003 Provenance Recording

The system shall generate a provenance record for every pipeline execution.

#### REQ-SCOPE-004 Candidate Persistence

The system shall persist archive discovery results as a candidate manifest file.

## 3. External interfaces and data sources

### Target resolution and archive search geometry

#### REQ-TARGET-001 Coordinate Precedence

The system shall resolve target coordinates from the target section of the scene card using the following precedence:

1. decimal coordinates
2. sexagesimal coordinates
3. name resolution

#### REQ-TARGET-002 Name Resolution Usage

The system shall perform name resolution from the target section only when explicit coordinates are not provided in the scene card.

#### REQ-TARGET-003 Circular Queries

The system shall issue circular region queries directly to the archive.

#### REQ-TARGET-004 Box Approximation

The system shall approximate rectangular search regions as circumscribed circles when querying the archive.

#### REQ-TARGET-005 Polygon Support

The system shall not perform polygon-based archive queries.

### MAST data and external discovery hints

#### REQ-DATA-001 Observation Query

The system shall query observations before querying products.

#### REQ-DATA-002 Observation Filtering

The system shall filter observations by mission and instrument.

#### REQ-DATA-003 Product Retrieval

The system shall retrieve product metadata in batches using observation identifiers.

#### REQ-DATA-004 Metadata Enrichment

The system shall propagate observation-level metadata to associated products.

#### REQ-DATA-005 Product Filtering

The system shall filter products by detector, filter, product type, and optional observation date range.

#### REQ-DATA-006 Candidate Manifest Generation

The system shall produce a candidate manifest containing all filtered candidate products.

#### REQ-DATA-007 Metadata Normalization

The system shall normalize mission-specific metadata fields, including filter names, product types, exposure time values, and observation date fields, into canonical internal representations prior to ranking or selection.

#### REQ-DATA-008 Total Ordering

The system shall produce a deterministic total ordering of all candidate products regardless of missing or equivalent metadata.

#### REQ-DATA-009 Selection-State Consistency

The system shall ensure that candidate selection fields are internally consistent. The final selection state shall reflect application of selection policy and user overrides.

#### REQ-DATA-010 Candidate identity consolidation

The system shall consolidate archive rows that identify the same downloadable product into one candidate before ranking, recommendation, persistence, or display.

#### REQ-DATA-011 Candidate metadata conflict handling

When consolidated archive rows disagree on metadata used for ranking or explanation, the system shall mark the affected field as conflicting and shall not silently present one conflicting value as authoritative.

#### REQ-DISC-001 Multiple Discovery Entry Points

The system shall support multiple user discovery entry points for finding candidate JWST scenes.

#### REQ-DISC-002 Discovery Role Separation

The system shall distinguish scene opportunity discovery from archive product discovery.

#### REQ-DISC-003 External Tracker Authority Boundary

The system shall treat external tracker records as discovery hints and shall not treat them as authoritative archive product manifests.

#### REQ-DISC-004 MAST Product Authority

The system shall use MAST as the authoritative source for archive product metadata, downloadable product identities, and candidate manifest records.

#### REQ-DISC-005 Discovery Hint Source Provenance

The system shall record the source URL, retrieval time, and extracted metadata for imported external discovery hints.

#### REQ-DISC-006 Discovery Hint Conversion

The system shall convert imported external discovery hints into scene card search inputs or user-facing search suggestions before archive product discovery.

#### REQ-DISC-007 External Discovery Failure Isolation

The system shall continue to support normal MAST discovery when an external discovery source fails.

#### REQ-DISC-008 Latest JWST Release Tracker Source

The system shall support the Yuval Harpaz latest JWST release tracker at `https://yuval-harpaz.github.io/astro/jwst_latest_release.html` as an external discovery hint source.

#### REQ-DISC-009 Discovery Hint Alignment

The system shall support an optional discovery-hint alignment rotation value expressed in degrees.

#### REQ-DISC-010 Alignment Rotation Bounds

The system shall accept discovery-hint alignment rotation values from 0 degrees through 360 degrees inclusive.

#### REQ-DISC-011 Alignment Default

The system shall default omitted discovery-hint alignment rotation values to 0 degrees.

### External interface requirements

#### REQ-IFACE-001 Name resolution boundary

The name resolver interface shall return resolved coordinates, target identity, and source attribution, or an explicit unresolved, ambiguous, or failed outcome.

#### REQ-IFACE-002 Archive failures

The MAST interface shall distinguish a successful query with zero candidates from a failed query.

#### REQ-IFACE-003 Incomplete results

The MAST interface shall identify incomplete result retrieval before those results can be presented as a complete candidate set.

#### REQ-IFACE-004 Download identity

Source download requests shall use the authoritative product identity associated with the selected MAST candidate.

#### REQ-IFACE-005 Unavailable product

When a selected product cannot be retrieved, the system shall identify that product and require an explicit selection change before substituting another product.

### Data source requirements

#### REQ-SOURCE-001 Name availability boundary

A resolved name shall not be presented as evidence that MAST has usable imaging data for that target.

#### REQ-SOURCE-002 Image attribution

An externally sourced discovery thumbnail shall retain its source URL and available credit information.

#### REQ-SOURCE-003 Preview distinction

The UI shall distinguish an external discovery image from a Galaxy-generated preview.

#### REQ-SOURCE-004 Cached result labeling

When cached archive results are displayed, the system shall expose their retrieval time and stale status.

## 4. Data definitions and persistence

### Application configuration and scene directory

Application configuration is separate from scene cards. For the repository-based distribution, project root means the root of the Galaxy source checkout containing the application, independent of the process working directory or Python executable location.

The initial application configuration is:

```json
{
  "scene_directory": "artifacts/scenes"
}
```

#### REQ-CONFIG-001 Configuration location and format

At startup, the system shall load application configuration from a UTF-8 JSON object in `galaxy.config.json` at the project root.

#### REQ-CONFIG-002 Default scene directory

When `scene_directory` is absent from application configuration, the system shall use `artifacts/scenes` relative to the project root as the default scene directory.

#### REQ-CONFIG-003 Missing configuration creation

When `galaxy.config.json` does not exist at startup, the system shall create it with `{"scene_directory": "artifacts/scenes"}` before resolving the effective scene directory, including when a command-line override is supplied.

#### REQ-CONFIG-004 Existing configuration preservation

Startup shall preserve an existing configuration file without rewriting it to insert defaults or persist command-line overrides.

#### REQ-CONFIG-005 Scene directory precedence

The system shall resolve the effective scene directory using the first specified value in this order: `--scene-dir`, application configuration `scene_directory`, built-in default.

#### REQ-CONFIG-006 Configuration path resolution

The system shall resolve a relative configured `scene_directory` against the directory containing `galaxy.config.json`.

#### REQ-CONFIG-007 Command-line path resolution

The system shall resolve a relative `--scene-dir` value against the process working directory at startup.

#### REQ-CONFIG-008 Configuration validation

Startup shall report invalid JSON, a non-object configuration, or a specified scene-directory value that is not a nonblank path string as a configuration error rather than treating it as an omitted value.

#### REQ-CONFIG-009 Configuration initialization failure

If the application configuration cannot be read or the missing configuration cannot be created, startup shall stop with a diagnostic identifying the configuration path and operation that failed.

#### REQ-CONFIG-010 Scene directory usage

The system shall use the effective scene directory as the Saved scenes library location and default destination for newly saved scene cards.

Absolute configured or command-line paths are used as absolute paths. Explicit user-selected scene-card paths remain supported. The setting is an application preference, not a field inside each scene card. A command-line override applies only to the current invocation.

### scene card contract

#### REQ-PROJ-001 Scene Card Artifact

The system shall persist each scene card as one UTF-8 JSON document conforming to [Scene card storage schema](scene_card_schema.md).

#### REQ-PROJ-002 Scene Card Purpose

The scene card shall contain the persisted scene definition, including partially completed inputs, selection constraints, frame, mapping, tone, optional processing settings, and artifact records.

#### REQ-PROJ-003 Scene Card Role Separation

The scene card shall reference binary source and generated artifacts without embedding their bytes in the JSON document.

#### REQ-PROJ-004 Scene Card Loadability

A render-ready scene card shall supply all user-authored configuration required for discovery, reprojection, and composition without a separate project file.

#### REQ-PROJ-005 Scene Card Saveability

The system shall be able to write a scene card reflecting the current user-selected settings from the UI or CLI workflow.

#### REQ-PROJ-006 Stable Round Trip

For a valid scene card, loading the file and saving it without user changes shall preserve semantic meaning and shall not lose defined fields.

#### REQ-PROJ-007 Unknown Field Handling

The system shall reject unknown scene card fields according to a documented validation policy.

#### REQ-PROJ-008 Required Top-Level Structure

The scene card shall support the sections defined in the scene card schema, including target, search, selection, canvas, planes, mapping, tone, psf, execution, discovery, assets, renders, and exports.

#### REQ-PROJ-009 Required Minimum Content

A newly created scene card shall be saveable with only the metadata fields required by the scene card schema.

#### REQ-PROJ-010 Validation

The system shall apply the scene card schema's action-specific readiness checks before discovery, rendering, or export.

#### REQ-PROJ-011 Search Constraints

The search section shall support optional constraints including:

- missions
- instruments
- detectors
- filters
- product types
- observation date range
- selection policy
- observation limits

#### REQ-PROJ-012 Exact Product Selection Support

When selection.selected_product_ids is present, those exact product identities shall take precedence over rediscovery-based source selection.

#### REQ-PROJ-013 Canvas Definition

The canvas section shall define the output sky projection and raster geometry including center, projection, pixel scale, width, height, and rotation.

#### REQ-PROJ-014 Saved View State

The scene card format shall support persistence of user-adjusted output view parameters that affect composition framing.

#### REQ-PROJ-015 Plane Activation

The planes section shall support enabling and disabling source planes and filters for downstream composition.

#### REQ-PROJ-016 Mapping Strategy

The mapping section shall support both:

- automatic mapping strategies
- explicit per-plane RGB contribution definitions

#### REQ-PROJ-017 Explicit Plane Mapping

When explicit per-plane mapping is present, the scene card shall be able to persist user-defined RGB assignments and labels for each mapped plane.

#### REQ-PROJ-018 Mapping Precedence

When explicit per-plane mapping is present, it shall take precedence over automatic mapping strategy fields.

#### REQ-PROJ-019 Tone Persistence

The tone section shall support persistence of user-adjusted presentation parameters including stretch, clipping, channel gain, channel bias, and saturation.

#### REQ-PROJ-020 Tone Scope

Tone parameters persisted in the tone section shall apply per output channel after plane mapping. Per-plane display normalization shall be persisted separately in the mapping section as required by REQ-NORM-001 through REQ-NORM-006.

#### REQ-PROJ-021 Execution Policy Separation

The execution section shall contain runtime policy settings and shall not alter the semantic meaning of the intended source scene or visual composition.

#### REQ-PROJ-022 UI Save Semantics

When the user saves a scene from the UI, the system shall write a scene card containing the current persisted scene definition and all user-adjustable settings designated as saveable.

#### REQ-PROJ-023 Saveable Adjustments

Saveable scene card settings shall include, at minimum:

- canvas framing parameters
- enabled and disabled planes
- explicit plane-mapping assignments
- tone and color-adjustment parameters
- PSF enablement state

#### REQ-PROJ-024 Non-Saveable Runtime State

Transient UI state not intended to affect reproducible output shall not be required to persist in the scene card.

#### REQ-PROJ-025 Search-Driven and Pinned Modes

The scene card shall support search-driven discovery and explicit product selection as defined by its schema.

#### REQ-PROJ-026 Scene Card Noncompliance Logging

The system shall log detected noncompliance with the current scene card format, including unknown fields, invalid values, unsupported section combinations, deprecated structures, and unsupported format revisions, with field-specific diagnostics.

### Scene card persistence requirements

#### REQ-CARD-001 Storage contract

Scene card reads and writes shall conform to [Scene card storage schema, revision 1](scene_card_schema.md).

#### REQ-CARD-002 Scene definition ownership

The system shall store executable scene settings directly in the scene card JSON document.

#### REQ-CARD-003 Selection pinning

Saving a scene with selected products shall persist their authoritative identities in selection.selected_product_ids.

#### REQ-CARD-004 Round trip

Saving and reopening a scene card shall preserve all defined persisted fields.

#### REQ-CARD-005 Safe save

A failed scene save shall leave the previous successfully saved scene readable.

#### REQ-CARD-006 Schema validation

Invalid scene card content shall produce field-specific diagnostics.

#### REQ-CARD-007 Unsupported revision

An unsupported scene card schema revision shall be rejected without modifying the stored scene.

#### REQ-CARD-008 Progressive completion

The system shall support saving a scene card with only the required metadata and adding optional sections as work progresses.

#### REQ-CARD-009 Artifact history

The system shall retain successful render and export records when later edits change the working scene definition.

#### REQ-CARD-010 Binary references

The system shall record thumbnails, source files, and generated images through asset references defined by the scene card schema.

#### REQ-CARD-011 Derived readiness

The system shall derive discovery, render, and export readiness from the current scene card contents.

#### REQ-CARD-012 Render input snapshot

Each successful render record shall retain the effective scene input snapshot used to produce that render.

#### REQ-CARD-013 Scene-owned artifact layout

Scene-owned source, processing, render, thumbnail, and retained-export artifacts shall use the directories and filenames defined by [Artifact storage specification, revision 3](artifact_storage_spec.md).

#### REQ-CARD-014 Cache separation

Regenerable application-cache paths shall not be persisted as portable scene-owned local asset paths.

#### REQ-CARD-015 Stable artifact identity

Artifact lookup and history shall use scene-card or authoritative archive identities rather than treating filenames as logical identities.

#### REQ-CARD-016 External export isolation

An external user-selected export destination shall remain separate from scene-owned render artifacts and shall not be modified merely by reopening a scene card.

#### REQ-CARD-017 Bounded asset verification

Local asset byte-count and checksum verification shall use bounded-memory streaming so that verification memory does not scale with source FITS file size.

#### REQ-CARD-018 Render-private scratch placement

Canonical scene execution shall place transient acquisition and processing scratch
below the current dedicated per-render working directory.

#### REQ-CARD-019 Scratch registration boundary

The system shall not register transient scratch as a portable scene asset or a
retained successful render output.

### Scene-card execution

#### REQ-EXEC-001 Exact selection execution

Pipeline execution from a scene card shall use exactly the product identities in `selection.selected_product_ids` and shall not re-run discovery or selection policy.

#### REQ-EXEC-002 Product retrieval identity

For each selected product, execution shall use its validated local source asset or its stored authoritative `data_uri`; it shall not substitute another product.

#### REQ-EXEC-003 Inspected plane validation

Before image processing, execution shall validate enabled filters, explicit mappings, derived-plane references, disabled planes, and PSF policies against plane identifiers and filter metadata read from the selected FITS products.

#### REQ-EXEC-004 Associated work directory

Canonical scene-card execution shall place generated working artifacts in the
dedicated per-render directory defined by the [Artifact storage
specification](artifact_storage_spec.md), within the scene card's associated asset
root, so recorded local asset paths cannot escape the scene.

#### REQ-EXEC-005 Successful render commit

After successful composition, execution shall append an immutable render record and its asset references to the scene card using atomic scene-card persistence.

#### REQ-EXEC-006 Failure history

Failed or incomplete processing shall not append a successful render record.

#### REQ-EXEC-007 Normal CLI format

The normal command-line interface shall accept JSON scene cards and shall not accept legacy YAML project files.

### One-time legacy translation

#### REQ-MIG-001 Original preservation

Legacy YAML translation shall leave the original project file unchanged.

#### REQ-MIG-002 New destination

Legacy translation shall refuse to overwrite an existing destination.

#### REQ-MIG-003 Translation verification

Legacy translation shall verify semantic equality between the committed JSON card and its reload.

#### REQ-MIG-004 Unresolved choices

Legacy translation shall report settings that require user review rather than inventing exact selected products, enabled filters, or resolved mapping coefficients.

#### REQ-MIG-005 Unsupported input

Legacy translation shall reject unsupported or ambiguous structures without publishing a scene card.

#### REQ-MIG-006 YAML retirement

After legacy translations are verified and the pipeline, UI, and CLI consume JSON scene cards, Galaxy-owned runtime YAML support and temporary translation tooling shall be removed.

### Candidate manifest

#### REQ-MAN-001 Manifest Format

The system shall produce a JSON candidate manifest.

#### REQ-MAN-002 Required Fields

Each candidate record shall include defined metadata fields including identifiers, observation metadata, and selection state.

#### REQ-MAN-003 Manifest Metadata

The manifest shall include generation time, scene card reference, selection policy, and selection inputs.

#### REQ-MAN-004 Unique candidate identity

A candidate manifest shall contain no more than one candidate record for each authoritative downloadable product identity defined by the selection guidance specification.

#### REQ-MAN-005 Scene query association

After a successful archive query, the active scene draft shall reference the persisted candidate manifest without requiring the user to apply a product recommendation.

#### REQ-MAN-006 Query-state restoration

Reopening a saved draft with an available referenced candidate manifest shall restore the candidate set, recommendation state, and retrieval metadata represented by that manifest without issuing a new archive query.

### Execution provenance

#### REQ-REPRO-001 Provenance Content

The system shall record:

- execution source
- selection policy
- selected candidate identifiers
- reprojection parameters
- memory estimate

### Discovery cache

#### REQ-CACHE-001 Cache Persistence

The system shall persist discovery results to disk.

#### REQ-CACHE-002 Cache Reuse

The system shall reuse persisted discovery results when query inputs are unchanged.

#### REQ-CACHE-003 Cache Expiration

The system shall treat persisted discovery results older than 6 months as stale unless explicitly reused.

#### REQ-CACHE-004 Forced Refresh

The system shall allow users to force a new archive query.

#### REQ-CACHE-005 Discovery cache placement

The system shall store newly written discovery-cache entries below
`<scene-directory>/.galaxy-cache/candidates/`.

## 5. User interface behavior

The screen flows are defined in [User flows](user_flows.md). Refinement contains Data, Color, and Frame sections; these are not additional top-level screens. Visual styling and pixel-exact layouts remain unspecified.

### Existing UI integration contracts

#### REQ-UI-001 Discovery Mode

The system shall support archive discovery and candidate selection.

#### REQ-UI-002 Preview Mode

The system shall support preview of aligned planes.

#### REQ-UI-003 Preview Branch Selection

When both original and PSF-processed aligned-plane artifacts are available for the same workdir, the preview UI shall allow the user to select which branch to preview.

#### REQ-UI-004 Selection Controls

The system shall allow per-candidate selection.

#### REQ-UI-005 Input Resolution

The UI entrypoint shall accept an explicit scene card or artifact path from a launch-time argument or environment-provided override.

Supported explicit inputs are scene card JSON, candidate manifest JSON, multi-plane FITS, or a workdir resolving to one of these artifacts. Scene cards and candidate manifests open Refinement; aligned-plane artifacts open Render.

Without an explicit input, the system shall open Discovery. Automatic workspace artifact discovery populates available choices without opening them; original aligned planes precede PSF-processed aligned planes, candidate manifests, and scene cards.

#### REQ-UI-006 Single-activation controls

A displayed radio button or checkbox shall commit its new value after one user
activation and shall retain that value through the resulting application rerun.

### Cross-screen behavior

#### REQ-NAV-001 Opening screen

On a normal launch without an explicit input, the system shall display Discovery (UF-01).

#### REQ-NAV-002 Screen navigation

The system shall provide the five-screen navigation and explicit-input routing defined in [User flows](user_flows.md).

#### REQ-NAV-003 Draft preservation

The system shall preserve unsaved scene edits when navigating between refinement, render, and output screens.

#### REQ-NAV-004 Unsaved departure

Before replacing or closing a scene with unsaved edits, the system shall offer Save, Discard, and Cancel.

#### REQ-NAV-005 Operation states

Each operation shall expose its applicable idle, running, succeeded, failed, or cancelled state as defined in the user flows.

#### REQ-NAV-006 Failure recovery

An operation failure shall preserve the scene edits that existed before the operation started.

#### REQ-NAV-007 Draft save access

Refinement and Render shall provide a save action for structurally valid incomplete scene cards.

### Discovery behavior — UF-01

#### REQ-FIND-001 Name search

Discovery shall accept a common name or catalog identifier as a target search input.

#### REQ-FIND-002 Alias matches

Discovery shall display the resolved target label for each matching name or alias.

#### REQ-FIND-003 Ambiguous names

Discovery shall require selection of a target when name resolution returns multiple possible targets.

#### REQ-FIND-004 Coordinate search

Discovery shall accept a coordinate pair and circular radius or rectangular search dimensions.

#### REQ-FIND-005 Thumbnail browsing

Discovery shall display thumbnail cards for available external discovery hints.

#### REQ-FIND-006 Missing thumbnails

A discovery hint without an available thumbnail shall remain selectable using a labeled placeholder.

#### REQ-FIND-007 Draft creation

Selecting a target or discovery hint shall open a new draft scene in Scene refinement.

#### REQ-FIND-008 Return context

Returning from refinement to Discovery shall restore the prior query, result filters, and gallery scroll position.

### Scene refinement behavior — UF-02

#### REQ-REFINE-001 Observation comparison

Refinement shall display archive observations as separately selectable groups keyed by authoritative archive observation identity.

#### REQ-REFINE-002 Observation details

Each observation group shall display available date, instrument, filters, exposure duration, and sky coverage, with missing values labeled unknown.

#### REQ-REFINE-003 Product inspection

Each observation group shall provide access to its candidate products and their individual selection controls.

#### REQ-REFINE-004 Filter selection

Refinement shall allow the user to enable or disable filters represented by the selected candidates.

#### REQ-REFINE-005 Selection guidance

Refinement shall display the recommended candidate selection produced by the configured REQ-SELECT policy and identify that policy.

#### REQ-REFINE-006 Filter guidance

Refinement shall recommend the distinct image filters represented in that recommended candidate selection.

#### REQ-REFINE-007 Mapping guidance

Refinement shall display a proposed RGB contribution for each enabled plane using the configured automatic mapping strategy.

#### REQ-REFINE-008 Guidance explanation

Each recommendation shall identify its basis and any metadata missing from that basis.

#### REQ-REFINE-009 Guidance acceptance

Applying a recommendation shall require a user action.

#### REQ-REFINE-010 Manual mapping

Refinement shall allow editing of per-plane RGB contributions.

#### REQ-REFINE-011 Default frame

Refinement shall display the scene card's configured canvas as the initial crop frame.

#### REQ-REFINE-012 Initial canvas

For a new scene without a configured canvas, refinement shall initialize a provisional TAN canvas centered on the resolved target, enclosing the search region at 1 arcsecond per pixel and zero rotation until selected FITS footprints are available.

#### REQ-REFINE-013 Frame editing

Refinement shall allow editing of frame center, width, height, rotation, and pixel scale.

#### REQ-REFINE-014 Footprint display

Refinement shall display available selected-observation footprints against the crop frame.

#### REQ-REFINE-015 Dependent validity

After observation or filter changes, refinement shall identify mapping references that no longer resolve to an enabled plane.

#### REQ-REFINE-016 Render gate

Refinement shall enable Render only when the scene card is render-ready, at least one usable image candidate is selected, and at least one enabled plane has a nonzero RGB contribution.

#### REQ-REFINE-017 Draft save

Refinement shall allow saving any structurally valid incomplete scene card as defined in [Scene card storage schema](scene_card_schema.md).

#### REQ-REFINE-018 Frame preservation

Changing observation or filter selections shall retain the current crop frame until the user explicitly edits or resets it.

#### REQ-REFINE-019 Selection summary

Refinement shall display the selection summary defined by the selection guidance specification for the current proposed selection before application and for the current applied selection after application.

#### REQ-REFINE-020 Unique summary counting

Selection summary counts and download-size estimates shall count each authoritative downloadable product identity no more than once.

#### REQ-REFINE-021 Selection modes

Refinement shall offer the `preview_set`, `one_per_filter`, and `custom` selection modes defined by the selection guidance specification.

#### REQ-REFINE-022 Selection scope

Refinement shall allow the user to constrain a recommendation to all available missions, HST, or JWST before applying it.

#### REQ-REFINE-023 Grouped candidate presentation

Refinement shall group candidates by mission, instrument, and normalized filter before displaying individual product alternatives.

#### REQ-REFINE-024 Recommended-row prominence

Each candidate group shall show its recommended product without requiring the user to expand the group's alternatives.

#### REQ-REFINE-025 Alternative disclosure

Nonrecommended products shall remain inspectable through an explicit alternatives control that displays the number of alternatives in the group.

#### REQ-REFINE-026 Concise recommendation explanation

Each displayed recommendation shall use the concise explanation format defined by the selection guidance specification and shall not expose internal reason codes as the primary user-facing explanation.

#### REQ-REFINE-027 Selection consequence labeling

Refinement shall identify whether the current recommendation is a bounded preview set, a full-filter set, or a custom selection.

#### REQ-REFINE-028 Explicit recommendation application

Changing a selection mode or scope shall update the proposed selection but shall not modify the scene card's applied product selection until the user invokes an explicit apply action.

#### REQ-REFINE-029 Selection reset controls

Refinement shall provide controls to clear the proposed selection and to restore the current mode's deterministic recommendation.

#### REQ-REFINE-030 Stage guidance

Before a product recommendation has been applied, Refinement shall present a concise ordered checklist for choosing data, applying the selection, reviewing color and frame, and rendering.

#### REQ-REFINE-031 Readiness summary

When Render is disabled, Refinement shall present unmet readiness conditions as user actions grouped by workflow stage.

#### REQ-REFINE-032 Technical readiness disclosure

Field paths and schema-level readiness diagnostics shall be hidden by default and available through a separately labeled technical-details disclosure.

#### REQ-REFINE-033 Initial selected-footprint fit

Before the first render of a new scene, after the selected and enabled FITS products are locally inspectable, Refinement shall replace the provisional search-region canvas with the fitted canvas defined by REQ-WCS-009 through REQ-WCS-016 when that fit has no geometric warning; a warned fit shall require the choice defined by REQ-REFINE-038.

#### REQ-REFINE-034 Fit selected scans action

Refinement shall provide a `Fit selected scans` action that recomputes the canvas from the current selected and enabled FITS products.

#### REQ-REFINE-035 Fit preview

Before applying a fitted canvas, Refinement shall display its center, angular width, angular height, rotation, pixel scale, raster dimensions, selected-product count, and geometric warning state.

#### REQ-REFINE-036 Explicit fit acceptance

Outside the automatic first-render initialization in REQ-REFINE-033, applying a fitted canvas shall require a user action.

#### REQ-REFINE-037 User-frame preservation

Changing selected products after a user has edited or accepted a canvas shall retain that canvas and shall identify each newly selected footprint that is not fully enclosed until the user invokes `Fit selected scans` or edits the frame.

#### REQ-REFINE-038 Geometric warning choices

When selected footprints meet a warning condition from REQ-WCS-014, Refinement shall offer the choices to revise the selection, continue with the fitted canvas, or keep the current canvas; it shall not silently create an extreme frame.

#### REQ-REFINE-039 Unusable footprint reporting

If any selected and enabled FITS product lacks a usable two-dimensional celestial footprint, automatic fitting shall stop and identify every affected product without claiming that the proposed canvas encloses all selected scans.

#### REQ-REFINE-040 Geometric fit visualization

Before a fitted canvas is applied, Refinement shall display an image of every
selected valid-support boundary projected into the proposed canvas together with
the proposed canvas border. A footprint overlay from an earlier render shall not
be presented as current when that render's canvas inputs differ from the active
canvas.

#### REQ-REFINE-041 Applied-selection reconciliation

When the user invokes `Apply selection and recommended defaults`, the system shall
preserve valid local source-asset references for unchanged product identities,
replace selection-dependent mapping and processing settings with deterministic
defaults for exactly the newly selected filters, remove references to unselected
filters or planes, retain the accepted canvas, and leave the resulting scene at a
renderable readiness state unless an independently reported frame, dependency, or
input problem remains.

### Render and adjust behavior — UF-03

#### REQ-RENDER-001 Preview generation

Render shall generate a preview from the current selected products and scene settings.

#### REQ-RENDER-002 Progress

During preview generation, Render shall display the active processing stage.

#### REQ-RENDER-003 Cancellation

Render shall provide cancellation that stops scheduling further stages after the running stage reaches a safe stopping point.

#### REQ-RENDER-004 Tone controls

Render shall expose the tone settings defined by REQ-PROJ-019.

#### REQ-RENDER-005 Mapping controls

Render shall allow editing of the persisted RGB mapping.

#### REQ-RENDER-006 Stale result

A change to selected products, canvas geometry, mapping, tone, or PSF settings shall mark the existing preview as out of date.

#### REQ-RENDER-007 Result identity

A successful preview shall record the scene content revision and processing branch used to produce it.

#### REQ-RENDER-008 Cancelled result

A failed or cancelled render shall not replace the last successful preview.

#### REQ-RENDER-009 Refinement return

Render shall provide a return path to Scene refinement for observation, filter, or crop changes.

### Output and save behavior — UF-04

#### REQ-SAVE-001 Export controls

Output shall allow selection of PNG or TIFF format, output pixel dimensions, and destination.

#### REQ-SAVE-002 Resolution framing

Changing output dimensions shall preserve the sky frame by retaining its aspect ratio and adjusting pixel scale.

#### REQ-SAVE-003 Current export

Export shall use a completed render matching the current scene settings and requested output dimensions.

#### REQ-SAVE-004 Named save

Output shall allow editing the scene card title before saving.

#### REQ-SAVE-005 Independent save

Saving a scene card shall not require successful image export.

#### REQ-SAVE-006 Thumbnail save

Saving a scene with a current successful preview shall store a thumbnail derived from that preview.

#### REQ-SAVE-007 Draft thumbnail

Saving a scene without a current successful preview shall retain available artifact history while using an attributed discovery thumbnail or placeholder as the current card image.

#### REQ-SAVE-008 Overwrite choice

Export to an existing output file shall require explicit overwrite confirmation.

#### REQ-SAVE-009 Separate outcomes

Output shall report scene-save and image-export outcomes independently.

### Saved scenes behavior — UF-05

#### REQ-LIB-001 Library access

Discovery shall provide access to Saved scenes.

#### REQ-LIB-002 Library cards

Saved scenes shall display each stored scene's title, thumbnail or placeholder, derived readiness, and last save time.

#### REQ-LIB-003 Reopen

Opening a saved scene shall restore its persisted scene definition into Scene refinement.

#### REQ-LIB-004 Duplicate

Duplicating a user-owned saved scene shall create a committed, independently
editable scene with a new scene identifier, content revision one, no render or
export history, and independently addressable retained input assets. Immutable
local input bytes may use same-volume hard links inside the new scene's asset root;
if linking is unavailable, duplication shall use a bounded-memory verified copy.
Deleting either scene shall not remove the other scene's input path. A missing or
invalid source asset shall fail duplication without publishing the new scene card.

#### REQ-LIB-005 Missing dependencies

Opening a scene with missing referenced assets shall identify those dependencies without silently replacing selected products.

#### REQ-LIB-006 Invalid entries

An invalid scene card shall be reported individually without preventing valid library entries from opening.

#### REQ-LIB-007 Bundled example discovery

The project selector shall discover valid bundled example scene cards from the source-controlled `<project-root>/examples/` directory independently of the configured user scene directory.

#### REQ-LIB-008 Scene origin label

The project selector shall label each bundled example separately from user-owned saved scenes.

#### REQ-LIB-009 Bundled example protection

The system shall not open a bundled example scene card as an editable scene or write changes to its source-controlled file.

#### REQ-LIB-010 Example-copy destination

The destination for a bundled example's user copy shall be the effective scene directory joined to the bundled example's exact filename, including filename casing.

#### REQ-LIB-011 Platform path deduplication

The project selector shall not display duplicate entries for filesystem paths that are equivalent under the active platform's path-casing rules.

#### REQ-LIB-012 Example-directory contents

The source-controlled `<project-root>/examples/` directory shall contain only UTF-8 JSON scene cards and shall not contain binary assets, thumbnails, caches, generated outputs, or non-JSON documentation.

#### REQ-LIB-013 Example duplication

When no destination file exists, Duplicate on a bundled example shall atomically copy the validated example JSON to the destination defined by REQ-LIB-010 without creating or copying a binary asset root.

#### REQ-LIB-014 Example overwrite confirmation

When the destination file already exists, Duplicate on a bundled example shall require explicit user confirmation before replacing that JSON file, and declining confirmation shall leave user data unchanged.

#### REQ-LIB-015 Example overwrite scope

Confirmed replacement of an existing example user copy shall replace only the destination JSON file and shall retain the matching user-owned binary asset root and all of its contents unchanged.

#### REQ-LIB-016 Example open resolution

Open on a bundled example shall open the existing user-copy destination when it exists; otherwise it shall perform the non-colliding duplication behavior in REQ-LIB-013 and then open the resulting user copy.

#### REQ-LIB-017 Example thumbnail source

The project selector shall display a bundled example's thumbnail only from the valid existing user copy and its referenced user-owned assets; when no usable user-copy thumbnail exists, it shall display a placeholder.

#### REQ-LIB-018 User-copy editing

After Open or Duplicate materializes a bundled example, all edits, saves, renders, downloads, and generated binary assets shall target the user copy and its associated user-owned asset root.

#### REQ-LIB-019 Example identity preservation

Materializing or replacing a bundled example user copy shall preserve the scene identifier stored in the bundled example JSON rather than minting a new identifier.

#### REQ-LIB-020 User-project deletion

Saved scenes shall provide a Delete action for each user-owned stored scene.

#### REQ-LIB-021 Bundled example deletion protection

The project selector shall not provide a Delete action for a source-controlled bundled example.

#### REQ-LIB-022 Deletion confirmation

Deleting a user-owned scene shall require explicit confirmation that identifies the scene title, scene-card path, and associated asset root before any filesystem change occurs.

#### REQ-LIB-023 Deletion scope

Confirmed deletion shall affect only the selected scene-card JSON and its associated asset root as defined by the artifact storage specification; it shall not delete application-cache entries, external exports, bundled examples, or another scene's files.

#### REQ-LIB-024 Recoverable deletion transaction

The normal Delete action shall move the selected scene card and its associated asset root as one recoverable unit; if both members cannot be moved, the system shall restore any moved member and report failure.

#### REQ-LIB-025 Active-operation guard

The system shall not begin deletion while a save, acquisition, render, or export operation associated with the selected scene is running.

#### REQ-LIB-026 Deletion outcome

After successful deletion, the system shall remove the scene from Saved scenes, close it if active, and display completion; cancellation or failure shall retain the active scene and refresh the library from the resulting filesystem state without reporting success.

#### REQ-LIB-027 Clone display title

Duplicating a user-owned scene shall set the new scene card's initial display title
to the source display title followed by ` copy`.

#### REQ-LIB-028 Clone storage name

The default JSON filename and associated asset-root name for a duplicated
user-owned scene shall derive their title slug from the source display title before
the ` copy` suffix required by REQ-LIB-027 is added, and shall use the duplicate's
new scene-ID prefix. The cloning operation shall not add its generated `copy` label
to either storage name.

#### REQ-LIB-029 Inline title-edit affordance

Each user-owned entry in Saved scenes shall present its displayed title as an
in-place rename affordance that can be activated by pointer or keyboard without
opening or editing the JSON file manually. Bundled-example source entries shall not
offer this edit affordance.

#### REQ-LIB-030 Inline title-edit state

Activating the rename affordance shall replace the displayed title in the same
card position with a focused single-line input prefilled with the complete current
title and explicit Commit and Cancel actions.

#### REQ-LIB-031 Inline title commit

Commit shall validate the proposed title under the scene-card title contract,
atomically persist the accepted title, update the Saved scenes card and any active
view of the same scene, and report success without requiring navigation away from
Saved scenes.

#### REQ-LIB-032 Inline title cancellation and failure

Cancel shall restore the unchanged displayed title. An empty, invalid, conflicting,
or failed title save shall retain the prior persisted title and storage paths and
shall display an actionable error adjacent to the affected card.

#### REQ-LIB-033 Title-edit identity and history preservation

Renaming a display title shall preserve the scene identifier, content revision,
JSON path, associated asset-root path, selected products, assets, renders, exports,
and current/stale render classification. Only title and save timestamp metadata may
change.

#### REQ-LIB-034 Title-edit operation guard

The Saved scenes rename affordance shall be unavailable while another write
operation for that scene is running, and simultaneous rename attempts shall use
the ordinary concurrent-save protection rather than silently overwriting a newer
scene document.

### Scene artifact inventory

#### REQ-ART-001 Inventory derivation

The system shall derive the displayed artifact inventory from scene-card selection, asset, render, and export records plus verification of referenced local files.

#### REQ-ART-002 Unreferenced file exclusion

The artifact inventory shall not claim an unreferenced filesystem entry as a scene artifact.

#### REQ-ART-003 Source availability states

The artifact inventory shall distinguish selected remote-only sources, available local sources, missing referenced sources, and corrupt referenced sources.

#### REQ-ART-004 Generated artifact states

The artifact inventory shall distinguish current renders, stale renders, aligned-plane sets, thumbnails, footprints, provenance, and export history.

#### REQ-ART-005 Empty category visibility

The artifact inventory shall display a zero or `None created` state for an empty required category.

## 6. Image processing behavior

### Deterministic selection

#### REQ-SELECT-001 Ranking Rule

The system shall rank candidate products within each observation/filter group using:

1. product type priority (`SCIENCE`, `DRZ`, `DRC`, `I2D`, `CAL`, others)
2. preference for image-like FITS products
3. newest product version
4. stable lexical identifier ordering

#### REQ-SELECT-002 Selection Policy

The system shall support selection policies defined by scene card search constraints and optional user overrides:

- all
- latest per filter
- deepest per filter

#### REQ-SELECT-003 Selection Limits

The system shall support scene-card-defined and user-overridden selection limits including:

- maximum observations per filter
- maximum total selected observations

#### REQ-SELECT-004 Explicit Overrides

The system shall apply explicit include and exclude selection overrides after ranking, using scene-card-defined search constraints and optional user overrides.

#### REQ-SELECT-005 Selection Persistence

The system shall record final selected candidates in both the candidate manifest and provenance record.

#### REQ-SELECT-006 Parent-observation product grouping

The system shall group an archive product by its authoritative parent observation
identifier and filter when that parent identifier is available, rather than
treating each detector or exposure product identifier as a separate observation.

#### REQ-SELECT-007 Combined-image preference

Within one parent observation and filter, automatic presentation-image selection
shall prefer an image-like Level-3 combined or association product over a
detector-level or exposure-level component product. An explicit product include or
user selection may override this recommendation.

#### REQ-SELECT-008 Unknown-depth semantics

For `deepest_per_filter`, a candidate with a known finite exposure duration shall
rank ahead of a candidate whose exposure duration is unknown. Candidates whose
durations are both unknown shall be ordered by the applicable product-role and
deterministic ranking rules and shall not be described as shallower based on the
missing duration.

#### REQ-SELECT-009 Unique selection identity

Automatic and user-modified selections shall contain each authoritative downloadable product identity no more than once.

#### REQ-SELECT-010 Preview-set policy

The `preview_set` mode shall recommend no more than three unique products and no more than one product for each normalized mission, instrument, and filter group.

#### REQ-SELECT-011 Full-filter policy

The `one_per_filter` mode shall recommend no more than one unique product for each normalized mission, instrument, and filter group within the selected mission scope and shall be presented as a full-filter set.

#### REQ-SELECT-012 Custom-selection policy

The `custom` mode shall preserve explicit user includes and excludes without adding automatic selections after the user begins editing the proposed selection.

#### REQ-SELECT-013 Selection-mode determinism

For identical normalized candidates, selection mode, mission scope, and explicit overrides, the system shall produce the same ordered recommendation.

#### REQ-SELECT-014 Recommendation explanation facts

The system shall derive recommendation explanations only from normalized candidate metadata, configured selection policy, crop-overlap measurements when available, and explicit user constraints.

#### REQ-SELECT-015 Download-size estimate

The system shall calculate estimated download size as the sum of known byte sizes for unique selected product identities and shall report selected products whose sizes are unknown separately.

### FITS ingestion

#### REQ-INPUT-001 FITS Loading

The system shall load FITS data and extract WCS information.

#### REQ-INPUT-002 Metadata Fallback

The system shall use PRIMARY header metadata when SCI metadata is unavailable.

### Reprojection

#### REQ-WCS-001 Configured Canvas

The system shall construct the output WCS from the canvas section of the scene card, including center, projection, pixel scale, width, height, and rotation.

#### REQ-WCS-002 Reprojection Surface

The system shall reproject all usable input planes onto the configured output canvas.

#### REQ-WCS-003 Processing Order

The system shall load all usable FITS planes prior to reprojection.

#### REQ-WCS-004 Reprojection Mode Recording

The system shall record reprojection mode in provenance.

#### REQ-WCS-005 Viewport-change invalidation

A change to canvas center, projection, pixel scale, dimensions, or rotation shall mark reprojection artifacts made for the previous canvas as stale for the current scene state.

#### REQ-WCS-006 Stale reprojection replacement

The system may overwrite or replace a stale reprojection artifact in the user-owned asset root when that artifact is not referenced by a retained successful render record in the current scene card.

#### REQ-WCS-007 Reprojection overwrite boundary

Reprojection replacement shall not overwrite downloaded source products or artifacts referenced by a retained successful render record.

#### REQ-WCS-008 Selected-plane overlap validation

Before composition, the system shall verify that every selected and enabled FITS
plane has nonzero measured footprint coverage on the configured output canvas. If
any plane has zero coverage, execution shall stop and identify each non-overlapping
source product; it shall not silently produce a composite that omits those planes.

#### REQ-WCS-009 Selected FITS footprint derivation

The system shall derive one celestial footprint for each selected and enabled FITS image from its two-dimensional celestial WCS and valid image support according to the selected-footprint viewport specification.

#### REQ-WCS-010 Spherical footprint union

The system shall combine selected footprints on the celestial sphere without treating right-ascension wraparound as a discontinuity.

#### REQ-WCS-011 Tight fitted orientation

The system shall project the footprint union onto a feasible local tangent plane and use the deterministic minimum-area enclosing rectangle defined by the selected-footprint viewport specification; no fixed north-up or instrument-aligned rotation is required.

#### REQ-WCS-012 Fitted-frame containment

The fitted canvas shall contain every derived selected footprint plus the specified padding on each side after integer raster dimensions are rounded upward.

#### REQ-WCS-013 Initial preview scale

The fitted initial canvas shall use a pixel scale no finer than the finest selected input scale and shall coarsen that scale as necessary to remain within the initial-preview raster limit defined by the selected-footprint viewport specification.

#### REQ-WCS-014 Geometric relationship warning

The system shall classify a fitted selection as geometrically suspicious when its footprints satisfy any disconnectedness, low-fill, excessive-separation, or absolute-span threshold in the selected-footprint viewport specification.

#### REQ-WCS-015 Framing diagnostics

The system shall report footprint-component count, total angular span, fitted-frame angular dimensions, footprint fill fraction, raster dimensions, and estimated memory whenever it presents a geometric relationship warning.

#### REQ-WCS-016 Tangent-plane feasibility

When the selected footprint union cannot be represented safely by one TAN canvas under the selected-footprint viewport specification, the system shall refuse automatic fitting and recommend revising the selection or creating separate scenes.

#### REQ-PERF-004 Memory Estimate Definition

The reprojection memory estimate shall be computed as a deterministic function of:

- output pixel count
- number of planes
- bytes per pixel
- reprojection method

For identical inputs, the same estimate shall be produced.

#### REQ-PERF-005 Memory Warning

The system shall emit a warning when estimated memory usage reaches at least 80% of installed system memory.

### Plane management

#### REQ-PLANE-001 Alignment

The system shall represent aligned data as multi-plane datasets.

#### REQ-PLANE-002 Enablement

The system shall support enabling and disabling planes.

#### REQ-PLANE-003 Reprojected Plane Format

The system shall persist reprojected plane artifacts in FITS format.

#### REQ-PLANE-004 Floating Pixel Support

The reprojected plane artifact format shall support at least 32-bit floating-point pixel values without display-oriented quantization.

#### REQ-PLANE-005 WCS and Source Metadata

Each persisted reprojected plane artifact shall include sufficient metadata to reconstruct the output-canvas sky alignment and the originating source-product identity.

#### REQ-PLANE-006 Multi-Plane Export Format

When the system exports an aligned plane set as a stacked artifact, it shall use a FITS-based representation.

### Mapping and tone

#### REQ-MAP-001 Composition

The system shall combine planes into RGB outputs using scene card mapping settings.

#### REQ-FITS-001 Native Unit Metadata

The system shall read each image plane's native `BUNIT` value when present and shall preserve that value through reprojection, aligned-plane export, provenance, and plane inventory reporting.

#### REQ-FITS-002 Validity Mask Sources

The FITS loader shall mark a science pixel invalid when a same-shape `DQ` value is nonzero, a same-shape `WHT` value is nonfinite or not greater than zero, or every applicable `CTX` sample is zero.

#### REQ-FITS-003 Validity Propagation

Invalid source pixels shall not contribute observed science values, observational coverage, or observation contribution diagnostics. Explicitly identified presentation estimates produced under REQ-BRIDGE-001 through REQ-BRIDGE-014 may contribute to presentation reprojection, display-normalization statistics, and RGB composition; they shall not be represented as observed samples.

#### REQ-FITS-004 Mask Provenance

The system shall record the FITS extensions used to construct each plane's validity mask and the valid coverage fraction after reprojection.

#### REQ-IMG-001 Required image validity

Every numerical image-stage input shall include an explicit boolean validity array
with the same raster shape, using the `True`-means-usable convention defined by
IMG-CONTRACT-001 and MASK-001 in the image-processing architecture.

#### REQ-IMG-002 Separate geometric coverage

Every numerical image-stage input shall include finite geometric coverage in
`[0,1]` separately from sample validity, and processing shall not interpret that
coverage as inverse variance or statistical weight.

#### REQ-IMG-003 Explicit processing domain

Every numerical image-stage input and output shall identify its processing domain
as defined by IMG-CONTRACT-001, and a stage shall reject an unsupported domain.

#### REQ-IMG-004 Aligned geometry identity

Every aligned numerical image-stage input and output shall carry its WCS, raster
shape, and stable grid identity; same-grid operations shall reject geometrically
incompatible operands according to IMG-CONTRACT-001.

#### REQ-IMG-005 Stage input ownership

A numerical processing stage shall not modify the values, validity, or coverage
arrays supplied by its caller.

#### REQ-IMG-006 Boundary validation

Numerical image packages shall be validated at processing boundaries for array
shape, finite usable values, coverage range, declared domain, and geometry as
specified by IMG-CONTRACT-001 and NUM-001.

#### REQ-DERIVED-001 Derived-plane support

A derived linear-combination or ratio plane shall carry validity and coverage
computed from every nonzero-weight operand by ARITH-001 and shall preserve the
common coordinate identity.

#### REQ-DERIVED-002 Singular ratio policy

A ratio result shall mark a sample invalid when its numerator or denominator lacks
support or when the absolute denominator does not exceed the persisted positive
threshold; adding an epsilon shall not make that sample valid.

#### REQ-NORM-001 Persisted Per-Plane Policy

The mapping section shall support a default display-normalization policy and an optional override on each explicit plane or filter mapping.

#### REQ-NORM-002 Normalization Modes

The system shall support `native` normalization and `percentile` display normalization. Omitted revision-one normalization settings shall resolve to `native` for backward compatibility.

#### REQ-NORM-003 Percentile Normalization

Percentile normalization shall calculate persisted black and white percentiles from finite valid pixels only, subtract the resulting black point, divide by the positive black-to-white interval, clip to `[0,1]`, apply the configured per-plane stretch, and then apply the configured nonnegative plane gain.

#### REQ-NORM-004 Processing Order

The system shall apply source validity masking and per-plane display normalization before RGB mapping weights, and shall apply output-channel tone processing after RGB composition.

#### REQ-NORM-005 Reproducible Diagnostics

Each composed plane shall record its effective normalization mode, native unit, black point, white point, gain, valid coverage fraction, and percentage contribution to every RGB channel.

#### REQ-NORM-006 Native Unit Warning

When enabled mapped planes contain more than one known native unit and any such plane uses `native` normalization, the system shall present a nonblocking warning that direct native-unit mixing can suppress planes.

#### REQ-NORM-007 New-Scene Display-Normalization Default

When render defaults are materialized for a scene that has no explicit plane
mapping, the system shall persist percentile display normalization with black
percentile `0.5`, white percentile `99.5`, an `asinh` stretch parameter of `4.0`,
and gain `1.0`. Loading an older revision-one scene that omits normalization shall
continue to resolve to `native` normalization as required by REQ-NORM-002.

#### REQ-NORM-008 Coverage-Aware Output Tone Statistics

Output-channel black and white percentiles shall be calculated only from finite
pixels supported by at least one valid contributing plane for that channel.
Pixels without valid contributing coverage shall remain zero after output tone
processing.

#### REQ-INV-001 Plane Inventory Fields

The plane inventory shall display mission, filter, processing level, product identity, filename, availability status, native unit, mask sources, normalization mode, black percentile, white percentile, plane gain, valid coverage, and RGB contribution.

#### REQ-INV-002 Unknown Inventory Values

Inventory values that cannot be determined before a successful render shall be displayed as `unknown` rather than inferred.

#### REQ-INV-003 Contribution Units

Plane RGB contribution shall be displayed as a percentage of the total absolute weighted signal in each output channel for the successful render.

#### REQ-INV-004 Warning Placement

Native-unit compatibility warnings shall be displayed adjacent to the source-plane inventory and shall not prevent inspection or editing.

#### REQ-TONE-001 Tone Processing

The system shall apply tone transformations using scene card tone settings.

#### REQ-TONE-002 Legacy Tone Compatibility

A tone section that omits an application mode, shared stretch, gamut policy, and
auto-stretch resolution shall retain the revision-one independent per-channel
tone result within the frozen legacy tolerance.

#### REQ-TONE-003 Shared-Intensity Application

When shared-intensity tone is selected, the system shall calculate
`L=(R+G+B)/3`, apply the selected monotone curve `T` to `L`, and multiply every
supported channel at that pixel by the same `T(L)/L` factor when `L` exceeds the
documented epsilon.

#### REQ-TONE-004 Shared-Intensity Domain

Shared-intensity tone shall reject a supported RGB sample containing a negative
channel after normalization, gain, and bias; an exactly zero intensity shall
produce zero without division by epsilon.

#### REQ-TONE-005 Gamut Policy

Shared-intensity tone shall provide explicit `clip` and per-pixel `rescale` gamut
policies. Ratio preservation may be claimed only before gamut handling and after
`rescale`, not after channel clipping.

#### REQ-TONE-006 Generalized Hyperbolic Stretch

The `ghs` method shall implement the forward generalized-hyperbolic construction
specified by TONE-GHS-001 using float64 intermediates and shall not copy GPL
implementation source.

#### REQ-TONE-007 GHS Parameter Validation

GHS shall require a stretch factor in `[0,20]`, local intensity in `[-5,15]`, and
`0 <= shadow_protection <= symmetry_point <= highlight_protection <= 1`.

#### REQ-TONE-008 GHS Identity and Continuity

A zero GHS stretch factor shall be the identity; every accepted GHS parameter set
shall produce finite, endpoint-normalized, monotone output continuous at the
shadow-protection, symmetry, and highlight-protection boundaries.

#### REQ-TONE-009 Auto-Stretch Proposal Source

An auto-stretch proposal shall use only finite shared-intensity samples selected
by persisted background inclusion and exclusion regions on the current branch and
grid, and shall report its reference identity and sample count.

#### REQ-TONE-010 Auto-Stretch Failure

Auto-stretch shall fail without fallback when the persisted sample is missing,
insufficient, constant, nonpositive at its resolved median, already above the
target placement, or classified as object-dominated by AUTOSTRETCH-001.

#### REQ-TONE-011 Auto-Stretch Apply and Recompute

Auto-stretch shall return a deterministic proposal containing requested targets,
resolved numerical settings, confidence diagnostics, and clipping estimates;
only explicit Apply shall change the scene, and Recompute shall create a new
proposal without changing the scene until applied.

#### REQ-TONE-012 Tone Controls and Persistence

The Render interface shall expose application mode, stretch method, applicable
method parameters, gamut policy, proposal diagnostics, Preview, Apply, Recompute,
and an identity/legacy choice. Applied values shall save, reopen, enter effective
render inputs and provenance, and make prior renders stale.

#### REQ-TONE-013 Single-Main-Stretch Preset

The interface shall provide an explicit single-main-stretch action that changes
per-plane display stretches to linear while selecting shared-intensity tone; it
shall not silently modify existing recipes.

### PSF processing

#### REQ-PSF-001 Dual Artifact Paths

The system shall preserve both the original image path and the PSF-processed image path as distinct artifact branches.

#### REQ-PSF-002 Optional Processing

The system shall perform PSF processing only when enabled for a plane or artifact branch.

#### REQ-PSF-003 Kernel Requirement

The system shall fail execution for the PSF-processed branch when PSF processing is enabled and no valid kernel is available for the corresponding source image.

#### REQ-PSF-004 Native-Frame Processing

The system shall apply instrument-specific PSF processing to the image artifact in the image frame for which the kernel is defined, prior to reprojection onto a shared canvas.

#### REQ-PSF-005 Cached PSF Artifact

When PSF processing is enabled, the system shall read the source FITS image and its kernel, generate a PSF-processed companion image, and store that companion artifact alongside the original cached source image.

#### REQ-PSF-006 Parallel Reprojection Branches

The system shall carry both original-image artifacts and PSF-processed artifacts through reprojection as separate branches.

#### REQ-PSF-007 Branch-Selective Composition

The system shall allow downstream composition to select either the original branch or the PSF-processed branch by artifact identity.

#### REQ-PSF-008 Dual Export Outputs

When both original and PSF-processed branches are present, the system shall generate PNG and TIFF outputs for both branches.

#### REQ-PSF-009 Processing Method

The system shall apply Richardson-Lucy deconvolution for the PSF-processed branch.

#### REQ-PSF-010 Validity-aware deconvolution

Richardson-Lucy processing shall exclude invalid observations from its forward
comparison and correction update according to PSF-RL-001, so changing finite
values underneath an invalid mask does not change valid output values.

#### REQ-PSF-011 Angular kernel sampling

A Gaussian PSF width expressed in angular units shall be converted to the native
pixel geometry according to PSF-GAUSS-001 before deconvolution; unsupported or
degenerate sampling geometry shall fail explicitly.

#### REQ-PSF-012 Signed-input policy

Richardson-Lucy processing shall reject a plane containing valid negative samples
with an actionable diagnostic and shall not silently clip those observations into
the nonnegative algorithm domain.

### Presentation bridging during reprojection

The [Native NaN bridge algorithm](reprojection_bridge_algorithm.md) defines
BRIDGE-MEDIAN-001, its eligibility profile, estimation method, support contracts
and acceptance cases for REQ-BRIDGE-001 through REQ-BRIDGE-021.

#### REQ-BRIDGE-001 Processing location

When a selected source FITS plane is loaded for full or reproject-only processing,
the system shall automatically bridge eligible native-frame missing-data clusters
in a separate presentation working copy when bridging is enabled. Preparation
shall follow science-data and archive-mask ingestion and precede original-branch
resampling onto the output grid.

#### REQ-BRIDGE-002 Default

The missing-data bridge shall be enabled by default when the setting is absent,
including for existing scene documents.

#### REQ-BRIDGE-003 Strict opt-out

When bridging is disabled, the system shall reproduce the existing strict
invalid-sample reprojection path without estimating missing values.

#### REQ-BRIDGE-004 Explicit control

The scene editor shall expose a two-state switch labelled "Bridge small NaN holes"
whose boolean saved value reaches both original and PSF-processed reprojection
branches. The switch shall display the effective default when the value is absent.

#### REQ-BRIDGE-005 Candidate mask

The candidate mask shall include samples invalid under REQ-FITS-002 and nonfinite
SCI samples; finite zero SCI samples with valid support shall not be candidates.

#### REQ-BRIDGE-006 Exterior exclusion

A candidate cluster connected to any native-image border through eight-connected
invalid samples shall remain unbridged.

#### REQ-BRIDGE-007 Bounded size

Eligibility shall require cluster area and maximum bounding-box extent to remain
within explicit configured positive limits expressed in native pixels.

#### REQ-BRIDGE-008 Local stellar evidence

Eligibility shall require valid neighboring samples to satisfy a deterministic,
versioned bright-core test with explicit thresholds independent of RGB mapping
and display stretch, as defined by BRIDGE-EVIDENCE-001 in the
[Native NaN bridge algorithm](reprojection_bridge_algorithm.md).

#### REQ-BRIDGE-009 Neighbor estimates

Eligible clusters shall receive finite estimates computed only from valid native
samples in a bounded local neighborhood using BRIDGE-FILL-001 in the
[Native NaN bridge algorithm](reprojection_bridge_algorithm.md).

#### REQ-BRIDGE-010 Rejection behavior

Clusters failing any eligibility criterion or lacking sufficient valid estimation
support shall retain strict invalid-sample handling.

#### REQ-BRIDGE-011 Source preservation

Bridging shall not modify archived FITS bytes or the ingested observation values
and validity masks.

#### REQ-BRIDGE-012 Estimate identity

Aligned artifacts shall distinguish observational support from presentation
support and retain a mask identifying output samples influenced by bridge
estimates, including influence through the resampling kernel.

#### REQ-BRIDGE-013 Reproducibility

Bridge enablement, thresholds, estimation method, algorithm version, candidate and
accepted cluster counts, and estimated-sample counts shall be recorded in render
provenance and incorporated into reprojection checkpoint identity.

#### REQ-BRIDGE-014 Performance accounting

The reprojection memory estimate shall include bridge working arrays, and bridge
elapsed time and peak-memory estimates shall be reported for benchmark fixtures.

#### REQ-BRIDGE-015 Branch isolation

Native PSF processing shall consume unchanged observation values and validity;
its output shall receive independent bridge preparation before reprojection.

#### REQ-BRIDGE-016 Persistence

Save, reopen, and duplicate shall preserve an explicitly selected bridge state.
Successful render history shall retain the effective state used by that render.

#### REQ-BRIDGE-017 Setting changes

Changing bridge state shall mark the current aligned result stale for the requested
settings and require full or reproject-only processing before generating a new
current preview or export. Historical results shall retain their recorded settings.

#### REQ-BRIDGE-018 Compose-only reuse

Compose-only processing shall reuse certified aligned bridge artifacts without
rerunning native bridging and reject checkpoints whose bridge settings, algorithm
version, or required support/influence artifacts do not match.

#### REQ-BRIDGE-019 Control explanation

The switch shall explain that On estimates eligible small enclosed bright-core
holes for presentation, Off preserves strict missing data, and changing the setting
requires reprojection. It shall not imply that every NaN is repaired.

#### REQ-BRIDGE-020 Execution snapshot

A running render shall use a fixed snapshot of bridge settings; the switch shall
be disabled while that scene has an active render operation.

#### REQ-BRIDGE-021 Preparation failure

An unexpected bridge preparation or numerical solver failure shall fail the render
with the source plane and reason identified, without publishing a successful result
or silently substituting strict processing. Eligibility rejection is a normal
recorded outcome rather than a preparation failure.

### Export artifacts

#### REQ-OUT-001 Output Formats

The system shall export presentation composites in PNG or TIFF format.

#### REQ-OUT-002 Reprojected Footprint Overlay

The system shall generate a visualization artifact with the same pixel dimensions as the configured output canvas showing the projected footprints of the selected source FITS images.

#### REQ-OUT-003 Reprojected Footprint Overlay Appearance

In the footprint overlay artifact, source-image boundaries shall be rendered as white outlines and all non-boundary pixels shall be rendered as black.

#### REQ-OUT-004 Reprojected Footprint Overlay Purpose

The footprint overlay artifact shall be intended for human inspection of how the selected archive assets map onto the configured output rectangle.

#### REQ-OUT-005 High-depth TIFF selection

An external TIFF export shall copy the matching successful render branch's
registered uint16 TIFF artifact and shall not transcode the preview PNG.

#### REQ-OUT-006 Explicit export branch

An external image export shall require an `original` or `deconvolved` branch and
shall select the matching current render and requested format role for that branch.

#### REQ-OUT-007 Missing output role

External export shall fail with an actionable error when the requested branch does
not register the requested output role.

## 7. Architecture and execution interfaces

### Pipeline constraints

#### REQ-ARCH-001 Pipeline Structure

The system shall execute processing as an ordered pipeline consisting of:

1. scene card validation
2. target resolution
3. archive discovery and selection
4. FITS ingestion
5. optional native-frame PSF processing on a separate derived branch
6. independent reprojection of the original and processed branches
7. plane management
8. branch-selective mapping and tone processing
9. export and provenance recording
10. provenance recording

#### REQ-ARCH-002 Stage Isolation

Each pipeline stage shall operate only on inputs produced by prior stages and shall not modify upstream artifacts.

#### REQ-ARCH-003 Tooling Compatibility

The system shall support debugger and launcher environments in which module-level argument forwarding is unreliable, without changing UI mode semantics.

### Processing checkpoints

#### REQ-CHK-001 Versioned aligned checkpoint

Every reusable aligned-plane FITS artifact shall have a versioned companion
manifest conforming to `docs/processing_checkpoint_spec.md`.

#### REQ-CHK-002 Producer dependency identity

A checkpoint shall be reused only when the SHA-256 key of its canonical numerical
producer inputs matches the requested upstream source, validity, branch, native
processing, canvas and reprojection inputs.

#### REQ-CHK-003 Downstream-setting exclusion

Mapping, display normalization, RGB tone, logging and output encoding settings
shall not invalidate an otherwise compatible aligned checkpoint.

#### REQ-CHK-004 Output integrity

A checkpoint shall be reused only after the companion FITS byte count and SHA-256
match the manifest and the loaded plane/grid summaries match the manifest.

#### REQ-CHK-005 Strict compose-only behavior

Compose-only execution shall reject a missing, legacy, corrupt or incompatible
checkpoint and shall not silently rebuild upstream processing.

#### REQ-CHK-006 Legacy inspection boundary

A legacy multi-plane FITS artifact without a checkpoint manifest may be inspected
through the explicit adapter but shall not be certified for compose-only reuse.

#### REQ-CHK-007 Algorithm version identity

Checkpoint producer inputs and stage records shall use stable algorithm
implementation versions rather than the application version or timestamps.

#### REQ-CHK-008 Atomic publication

A checkpoint manifest shall become reusable only after its FITS output is complete,
and failure or cancellation shall not register it as a successful scene asset.

#### REQ-RENDER-010 Shared numerical render core

Scene composition and direct aligned-stack preview shall use the same numerical
composition and tone function; equal packages and equal settings shall yield equal
floating RGB output including partial-support behavior.

#### REQ-PROV-010 Stage record completeness

Each persisted processing stage record shall contain its stable stage and algorithm
IDs, versions, parent/source identities, branch, input/output domain and grid,
requested settings, resolved settings and output content identity.

### Background pedestal correction

#### REQ-BG-001 Persisted sky regions

Pedestal estimation shall use persisted ICRS inclusion rectangles and optional
ICRS exclusion rectangles rasterized at aligned-grid pixel centers according to
BG-PED-001, independently of viewport coordinates.

#### REQ-BG-002 Common valid samples

Every participating plane in a branch shall use the same geometric sky selection
intersected with the common finite-valid, positive-coverage sample mask, and shall
report the geometric and common-valid sample counts and fraction.

#### REQ-BG-003 Deterministic robust estimator

Pedestal proposals shall use the deterministic sigma-clipped median, thresholds,
failure states and diagnostics specified by BG-PED-001.

#### REQ-BG-004 Explicit proposal and application

Automatic pedestal estimates shall be presented as explicit proposals and shall
not affect canonical rendering until resolved per-plane values and their numerical
identity are applied to the scene.

#### REQ-BG-005 Linear correction contract

Applied pedestals shall be subtracted only from valid aligned-linear samples before
derived arithmetic and display normalization, while preserving signed residuals,
coverage, celestial WCS, grid, branch and lineage and retaining the pre-correction
aligned checkpoint.

#### REQ-BG-006 Unsupported sampling

Missing regions, incompatible grids, identity mismatches or insufficient samples
shall fail visibly and shall not silently select the whole frame, reuse stale
values or produce an inferred correction.

#### REQ-BG-007 Diagnostics and provenance

Each applied branch shall persist requested estimator/region settings, resolved
per-plane values, common-sample diagnostics, a viewable region overlay and a
background stage record conforming to PROV-001.

#### REQ-BG-008 User workflow

The UI shall provide pedestal proposal preview, Apply and disable controls, show
the region overlay and before/after diagnostics, and persist applied settings so
save/reopen, rendering and export reproduce the same correction.

#### REQ-NORM-009 Background-referenced black policy

The `corrected_zero` policy shall use corrected native zero as the plane and mapped
channel black reference without recomputing a black percentile; the separate
`legacy_percentile` policy shall preserve prior behavior as specified by
NORM-BG-001.

### Presentation coverage and stable normalization

#### REQ-COV-001 Explicit presentation policy

Each scene shall independently persist an output-footprint policy and a tone-
reference policy. Output footprint shall be `available_contributors` or
`common_required_bands`; tone reference shall be `output_support` or
`common_required_bands`. Omitted fields shall resolve to legacy union output and
output-support tone statistics, while newly materialized recommended defaults
shall use union output with common-required-band tone statistics.

#### REQ-COV-002 Required-band identity

Common required-band support shall intersect finite-valid, positive-coverage
support for every enabled mapped plane having at least one nonzero RGB weight and
for every source dependency of a mapped derived plane.

#### REQ-COV-003 Unsupported samples

Union output shall retain every channel sample having a valid contributor. The
same tone transform resolved from the configured reference pixels shall be applied
to partial-support samples without division by contributor count, local gain
adjustment, synthesis, interpolation, or relabeling. Common-only output shall set
all RGB channels to zero outside the common mask.

#### REQ-COV-004 Empty and disconnected support

An empty common mask shall stop composition when either output footprint or tone
reference requires common support. Disconnected components shall all remain
selected; no component shall be silently preferred or discarded, and internal
holes shall remain unsupported.

#### REQ-COV-005 Optional bounding crop

The `bounding_box` crop mode shall enclose every component of the selected output support,
expand each bound by the persisted nonnegative integer padding, clip the expansion
to the original raster, and update celestial WCS by the exact applied pixel slice.
The `none` mode shall preserve the original raster dimensions and WCS.

#### REQ-COV-006 Stable tone domain

When tone reference is `common_required_bands`, each output channel's black and
white statistics shall use the uncropped common mask, while the resulting transform
shall be applied over that channel's selected output-valid samples. Changing output
footprint, crop mode, or padding alone shall not change numerical tone results for
pixels common to the compared outputs.

#### REQ-COV-007 Coverage diagnostics

Each composed branch shall report the output and tone-reference policies, crop mode and padding,
required mapped planes and source dependencies, union and common pixel counts,
common-to-union fraction, connected-component count, excluded pixel count, and
applied crop bounds and output shape.

#### REQ-COV-008 Coverage workflow

The UI shall display independent output-footprint and brightness-reference controls
plus crop controls, preview the output and diagnostics before Apply, and persist
applied settings across save and reopen. Applied changes shall make prior renders stale.

#### REQ-NORM-010 Fixed numerical bounds

Per-plane display normalization shall support persisted finite `black_value` and
`white_value` bounds, require `black_value < white_value`, and use those values
without percentile re-estimation.

#### REQ-NORM-011 Region-derived normalization proposal

The system shall calculate a normalization proposal only from an explicitly
selected persisted Phase 3 inclusion region after applying its exclusions and the
common finite-valid, positive-coverage sample mask. Empty, incompatible, or
constant samples shall fail visibly.

#### REQ-NORM-012 Locked normalization reference

Applying a region-derived proposal shall persist its region identities, branch,
grid, source identities, native unit, coverage policy, requested percentiles,
resolved bounds, sample count, clipping fractions, and locked state. Rendering
shall consume the resolved bounds and shall not recompute them implicitly.

#### REQ-NORM-013 Explicit recomputation

Recomputing a region-derived reference shall require an explicit user action,
replace the resolved reference with newly recorded values, and invalidate only
downstream render products.

#### REQ-NORM-014 Normalization workflow

The UI shall distinguish legacy percentile, fixed-value, and applied
region-reference normalization, show resolved bounds and clipping fractions, and
support preview, Apply, save, reopen, and consistent original/deconvolved branch
behavior.

### Command-line interface

#### REQ-CLI-001 Discovery Command

The system shall support a discovery command that outputs a candidate manifest.

#### REQ-CLI-002 Execution Command

The system shall support execution using a scene card and optional selection manifest.

#### REQ-CLI-003 Execution Modes

The system shall support full, download-only, reprojection-only, and compose-only modes.

#### REQ-CLI-004 Scene directory override

The application launcher shall accept `--scene-dir <path>` to override the configured scene directory according to REQ-CONFIG-005.

## 8. Diagnostics and verification

### Logging

#### REQ-LOG-001 Discovery Logging

The system shall log archive query progress and counts.

#### REQ-LOG-002 Download Logging

The system shall log download progress and failures.

#### REQ-LOG-003 Reprojection Logging

The system shall log reprojection parameters and memory warnings.

#### REQ-LOG-004 Scene Card Validation Logging

The system shall log scene card validation failures with field-specific diagnostics sufficient to identify the noncompliant field or section.

#### REQ-LOG-005 Scene Card Format Noncompliance Logging

The system shall log any detected noncompliance with the current scene card format, including unknown fields, invalid values, unsupported combinations, deprecated structures, and unsupported format revisions.

#### REQ-LOG-006 Logging Severity Scheme

The system shall implement a system-wide logging severity scheme with at least the following levels:

- ERROR
- WARNING
- INFO
- DEBUG

#### REQ-LOG-007 Severity Semantics

The system shall use logging severities consistently according to the following intent:

- ERROR for failures, noncompliance, or conditions that prevent successful completion of a required operation
- WARNING for abnormal or degraded conditions that do not prevent continued operation
- INFO for routine operational milestones, progress events, and major state transitions
- DEBUG for detailed diagnostic information intended primarily for troubleshooting and development

#### REQ-LOG-008 Console Logging Sink

The system shall emit logs to the console during execution.

#### REQ-LOG-009 File Logging Sink

The system shall persist logs to a file during execution.

#### REQ-LOG-010 Dual-Sink Consistency

The system shall use the same system-wide logging severity scheme for both console and file logging sinks.

#### REQ-LOG-011 Log Record Content

Each log record shall include, at minimum:

- a timestamp
- a severity level
- a message

#### REQ-LOG-012 Debug Visibility Control

The system shall support configuration of whether DEBUG-level log records are emitted to console, file, or both.

### Testing

#### REQ-TEST-001 Unit Coverage

The system shall provide automated tests for core pipeline logic.

#### REQ-TEST-002 Offline Testability

Core behaviors shall be testable without network access.

### Contract transition

The scene card replaces the former YAML project concept. Historical REQ-PROJ identifiers remain stable labels for the revised scene card contract. Existing YAML loaders and their tests are legacy implementation evidence, not the normative storage definition. Phase 2 supplies JSON scene-card persistence and isolated one-time translation. Pipeline, CLI, and screen integration remain tracked implementation gaps. Galaxy-owned YAML support is removed after verified translation and consumer cutover.

## 9. Limitations and deferred proposals

The system does not currently support:

- polygon-based archive queries
- advanced astrometric refinement
- empirical PSF fitting
- physically exact PSF transport through reprojection for a single-kernel post-reprojection workflow

The search-region enclosure is provisional until selected FITS footprints can be inspected. The target behavior for initial and user-requested fitting is defined by REQ-REFINE-033 through REQ-REFINE-039, REQ-WCS-009 through REQ-WCS-016, and the [selected-footprint viewport specification](viewport_framing_spec.md). Implementation remains tracked by GAP-FRAME-001.

Local name-catalog acquisition, fuzzy matching, category browsing, “Surprise me,” automatic cross-observation mosaics, and a sky-map browsing screen remain proposals. They require separate accepted requirements before implementation.

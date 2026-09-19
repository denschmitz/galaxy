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
- [UI acceptance coverage](testing/ui_scene_coverage.md): planned acceptance scenarios and implementation gaps.
- [Known gaps](compliance_status/known_gaps.md): unresolved implementation and specification work.

Requirements take precedence over flows; the storage schema supplies field-level definitions referenced by REQ-CARD-001. Supporting documents must be updated together when a contract changes.

### Behavioral definitions

| Term | Meaning |
| --- | --- |
| Discovery hint | A source-attributed suggestion of a target or sky region; archive availability is unverified. |
| Scene | Target or region plus data selection, frame, and composition settings. |
| Scene card | The canonical JSON project document, containing scene inputs, settings, selected source identities, and artifact records; optional associated files hold binary assets. |
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

Tone parameters persisted in the scene card shall apply per output channel. Per-plane tone persistence is not required unless explicitly introduced by a future schema revision.

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

Scene-owned source, processing, render, thumbnail, and retained-export artifacts shall use the directories and filenames defined by [Artifact storage specification, revision 1](artifact_storage_spec.md).

#### REQ-CARD-014 Cache separation

Regenerable application-cache paths shall not be persisted as portable scene-owned local asset paths.

#### REQ-CARD-015 Stable artifact identity

Artifact lookup and history shall use scene-card or authoritative archive identities rather than treating filenames as logical identities.

#### REQ-CARD-016 External export isolation

An external user-selected export destination shall remain separate from scene-owned render artifacts and shall not be modified merely by reopening a scene card.

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

For a new scene without a configured canvas, refinement shall initialize a TAN canvas centered on the resolved target, enclosing the search region at 1 arcsecond per pixel and zero rotation.

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

Duplicating a saved scene shall create an independently editable draft with a new scene identifier.

#### REQ-LIB-005 Missing dependencies

Opening a scene with missing referenced assets shall identify those dependencies without silently replacing selected products.

#### REQ-LIB-006 Invalid entries

An invalid scene card shall be reported individually without preventing valid library entries from opening.

#### REQ-LIB-007 Bundled example discovery

The project selector shall discover registered bundled example scene cards independently of the configured user scene directory.

#### REQ-LIB-008 Scene origin label

The project selector shall label each bundled example separately from user-owned saved scenes.

#### REQ-LIB-009 Bundled example protection

An ordinary save operation shall not overwrite a bundled example scene card.

#### REQ-LIB-010 Bundled example save-as

Saving changes made after opening a bundled example shall create a user-owned scene with a new scene identifier in the configured user scene directory.

#### REQ-LIB-011 Platform path deduplication

The project selector shall not display duplicate entries for filesystem paths that are equivalent under the active platform's path-casing rules.

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

#### REQ-TONE-001 Tone Processing

The system shall apply tone transformations using scene card tone settings.

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

### Export artifacts

#### REQ-OUT-001 Output Formats

The system shall export presentation composites in PNG or TIFF format.

#### REQ-OUT-002 Reprojected Footprint Overlay

The system shall generate a visualization artifact with the same pixel dimensions as the configured output canvas showing the projected footprints of the selected source FITS images.

#### REQ-OUT-003 Reprojected Footprint Overlay Appearance

In the footprint overlay artifact, source-image boundaries shall be rendered as white outlines and all non-boundary pixels shall be rendered as black.

#### REQ-OUT-004 Reprojected Footprint Overlay Purpose

The footprint overlay artifact shall be intended for human inspection of how the selected archive assets map onto the configured output rectangle.

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
- robust geometric output derivation for mixed footprints
- physically exact PSF transport through reprojection for a single-kernel post-reprojection workflow

The initial canvas is a search-region enclosure, not an automatic optimal crop of mixed observations. For a circle, the unrotated bounding square has side twice the radius; for a rectangle, use its supplied dimensions. Round pixel dimensions upward. A discovery hint with no usable region requires user-supplied dimensions before initialization.

Local name-catalog acquisition, fuzzy matching, category browsing, “Surprise me,” automatic cross-observation mosaics, and a sky-map browsing screen remain proposals. They require separate accepted requirements before implementation.

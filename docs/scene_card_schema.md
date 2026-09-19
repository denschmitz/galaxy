# Scene Card Schema — Preliminary Revision 1

## 1. Concept and authority

A **scene card** is Galaxy's project file: one UTF-8 JSON document containing everything needed to describe and resume work on a scene. It starts small and expands as the target, observations, composition, thumbnails, renders, and exports are defined.

The card stores structured data and references; binary images, FITS files, and other large artifacts live in an optional associated asset directory or the shared source cache. There is no separate YAML project file and no required per-scene settings sidecar.

This specification defines the contract referenced by REQ-PROJ-001 and REQ-CARD-001 in [Design requirements](design_requirements.md). The companion [JSON Schema](scene_card.schema.json) defines structural validation; Python action and reference checks enforce cross-field rules. The [artifact storage specification](artifact_storage_spec.md) defines normative filesystem names and placement. [User flows](user_flows.md) describes how screens populate it.

## 2. File and asset layout

The default scene-card directory is `<project-root>/artifacts/scenes`. Application configuration in `<project-root>/galaxy.config.json` can change it using `scene_directory`; `--scene-dir <path>` takes precedence for the current invocation. Missing application configuration is created with the default value. See REQ-CONFIG-001 through REQ-CONFIG-010 and REQ-CLI-004 in [Design requirements](design_requirements.md).

This location setting belongs to application configuration, not the scene card schema. Relative configuration paths are based on the configuration directory; relative command-line paths are based on the startup working directory.

A card can also be saved at an explicit user-selected path. The normative directory
layout and name derivation rules are defined by the [artifact storage
specification](artifact_storage_spec.md). A minimal example is:

```text
horsehead-nebula-12345678.scene.json
horsehead-nebula-12345678.assets/
    inputs/
    renders/
    exports/
```

The asset folder is optional until a local artifact exists. Local asset paths are
relative to the JSON file's directory and confined to its associated asset root.
Moving the card with its associated folder preserves those references. Cached
archive data can instead be referenced by authoritative archive URI and cached by
the application. External source URLs remain attribution, not a promise of offline
availability.

The display title is independent of the filename. The library discovers cards by their scene-card type marker, not by mistaking every JSON document for a scene card.

## 3. Top-level fields

Only the first seven metadata fields are required in a newly saved card. All other fields are optional and can be added when their information becomes available.

| Field | Type | When present / meaning |
| --- | --- | --- |
| document_type | string | Required; exactly galaxy.scene_card. |
| schema_version | integer | Required; exactly 1. |
| scene_id | string | Required; canonical lowercase UUID, stable across edits. |
| title | string | Required; nonblank. Creation may supply Untitled scene. |
| created_at | string | Required; UTC RFC 3339 timestamp ending Z. |
| updated_at | string | Required; UTC RFC 3339 timestamp ending Z, not before created_at. |
| content_revision | integer | Required; at least 1; revision of scene-defining inputs. |
| description | string | Optional user notes. |
| target | object | Name and/or coordinates, with search region. |
| search | object | Archive search constraints and selection policy. |
| discovery | object | Source provenance and optional cached discovery references. |
| selection | object | Selected observations, source products, and exact product identities. |
| canvas | object | Output sky frame and raster geometry. |
| planes | object | Plane/filter activation. |
| mapping | object | Automatic mapping strategy and explicit RGB contributions. |
| tone | object | Channel stretch, clipping, gain, bias, and saturation. |
| psf | object | Optional PSF processing configuration. |
| execution | object | Runtime policy; does not define scene appearance. |
| assets | object | Map from locally unique asset IDs to asset records. |
| thumbnail_asset_id | string | Optional reference to the current card thumbnail in assets. |
| renders | array | Successful preview/render records, retained as history. |
| exports | array | Successful exported-image records. |
| output | object | User choices for the next export. |

Optional fields are omitted until known. JSON null is not accepted in revision 1; omission has the defined meaning above. Empty arrays/maps mean a known empty collection. Search constraint lists explicitly use an empty list to mean no restriction, as specified in section 5; an empty selected-product list always means no selection. Omitted selection is unfinished selection.

Unknown fields are rejected, except within discovery.sources[].extracted_metadata, which deliberately preserves source-specific JSON data. Future additions require a schema revision or an explicit extension specification; readers must not silently discard fields.

## 4. Progressive completion and action readiness

Lifecycle states are derived from content, not stored in a mutable status field. A card can retain earlier renders while current settings are incomplete or changed.

| Milestone/action | Additional required content | Typical screen |
| --- | --- | --- |
| Create or save draft | Required metadata only; every supplied value is structurally valid. | Discovery or any editing screen |
| Resolve a name | target.name, unless coordinates have already been supplied. | Discovery |
| Search MAST | Resolved decimal or sexagesimal coordinates and target.region; applicable search defaults materialized. | Refinement |
| Select data | selection.products and nonempty selection.selected_product_ids. | Refinement |
| Render current scene | Resolved canvas, selected usable products, complete plane/mapping/tone/PSF settings, valid references, and nonzero contribution from an enabled plane. | Render |
| Attach discovery thumbnail | Discovery asset with attribution and thumbnail_asset_id. | Discovery/refinement |
| Attach generated thumbnail | Successful render record and its thumbnail asset. | Render/save |
| Export | Successful matching render, requested output format/dimensions, and destination. | Output |
| Reopen | Structural validity; missing binaries are checked as dependencies. | Saved scenes |

“Render-ready” does not mean files are currently cached or downloadable. Retrieval failure is separate. Rendered history does not mean the current revision has been rendered.

Partial objects are allowed during drafting: target may initially contain only name; canvas may contain only center; tone may contain only a chosen stretch kind. Supplied members must have valid types and bounds. Missing members are identified by action-readiness checks, not replaced with invented values. Incomplete text that is not a valid field value must be corrected or explicitly cleared before saving.

Resolved coordinates, applied recommendations, and concrete default values are saved when accepted or used for an action. Saved cards do not depend on whatever defaults a later application release happens to choose.

## 5. Target, discovery, and archive selection

### target

| Member | Type / bounds | Semantics |
| --- | --- | --- |
| name | nonblank string | User-facing target name or identifier. |
| resolved_name | nonblank string | Resolver's selected identity when available. |
| ra_deg, dec_deg | finite numbers; RA [0,360), Dec [-90,90] | Decimal coordinates; a complete pair is required when this representation is used. |
| ra, dec | nonblank strings | Sexagesimal coordinate pair; must parse before use. |
| coordinate_frame | string, ICRS | Coordinate frame for revision 1. |
| region | object | Circle: kind=circle, radius_arcmin>0. Box: kind=box, width_arcmin>0, height_arcmin>0. |

Coordinates take precedence over name resolution, with decimal coordinates preceding sexagesimal coordinates. Conflicting supplied representations are diagnosed before search. Partial pairs are draft-only. Polygon queries remain outside scope. Moving-target ephemerides are not represented by a fixed coordinate cache.

### search

Optional members: missions, instruments, detectors, filters, product_types (arrays of nonblank strings); observation_date_start/end (ISO 8601 UTC timestamps, ordered start <= end); observation_selection (all, latest_per_filter, or deepest_per_filter); max_observations_per_filter and max_total_observations (positive integers).

Omitted constraint arrays mean no restriction for that field. Explicit empty constraint arrays also mean no restriction; this differs from an empty selected-product list, which means no selection. At search time, the effective selection policy is explicit. Display grouping follows authoritative observation identity, not target-name equality.

### discovery

Optional members: sources (array of source records), candidate_manifest_asset_id (asset reference), archive_retrieved_at (UTC timestamp).

Each source record requires source_kind (release_tracker or name_resolver), source_url (HTTP(S)), retrieved_at (UTC timestamp), and extracted_metadata (JSON object). Available thumbnail credit and source-specific alignment rotation may be retained in the payload; alignment rotation is bounded 0 through 360 degrees and defaults to zero when used. MAST product metadata remains authoritative.

### selection

| Member | Type | Meaning |
| --- | --- | --- |
| products | array | Product records known to the current selection. |
| selected_product_ids | array of unique strings | Exact authoritative product identities selected for this scene. |
| observation_ids | array of unique strings | Optional grouping identities for display. |

Every selected_product_ids entry must match one products[].product_id before rendering. A product record requires product_id (nonblank authoritative stable identifier). Optional members: archive (MAST), data_uri, observation_id, mission, instrument, detector, filter, product_type, product_version, filename, exposure_seconds (finite >=0), observed_at (UTC timestamp), cached_asset_id (asset reference). Download requires data_uri or a successful authoritative lookup by product_id. Records must not synthesize metadata that MAST did not provide.

product_id is the pin: saved selection cannot be silently replaced by a newer version. Re-querying can propose additions or replacements for user acceptance. Unknown observation associations remain unknown rather than merging unrelated products.

## 6. Frame and composition

All members below are optional in a draft. The Render readiness check requires the effective settings used by the pipeline to be explicitly stored.

### canvas

center: object with mode=explicit and ra_deg/dec_deg, or mode=resolved_target. Render requires an explicit resolved center.
projection: TAN in the initial UI profile.
pixel_scale_arcsec: finite number >0.
width and height: positive integers.
rotation_deg: finite number in [0,360); normalize 360 to zero.
flux_conserving: boolean.
view_state: optional object with zoom (>0), pan_x, pan_y (finite numbers).

The canvas defines the output sky frame. View state affects only the saved presentation view; a crop change must update canvas geometry. Resolution changes preserve sky extent by adjusting pixel scale and retaining aspect ratio.

### planes

enabled_filters: array of unique nonblank filter identifiers.
disabled_plane_ids: array of unique nonblank plane identifiers.
export_multiplane_fits: boolean.

Omitted activation settings are unfinished until materialized. An empty enabled_filters array enables no filters and fails Render readiness. Disabled plane IDs override filter enablement.

### mapping

defaults: object with strategy=continuum or wavelength_order.
planes: array of explicit contribution objects, each containing exactly one selector (plane or filter), optional label, and rgb with finite red, green, blue values.
derived_planes: optional array of derived-plane definitions.

Explicit contributions take precedence over the automatic strategy. Render readiness requires concrete resolved contributions for enabled planes so the saved appearance does not depend on changing recommendation logic. Contributions may be negative for subtraction; at least one enabled plane must have a nonzero contribution. Every selector must resolve. Duplicate selectors are rejected.

A derived-plane definition requires name and operation (linear_combination or ratio). A term is {plane: nonblank string, weight: finite number}. linear_combination requires a nonempty terms array. ratio requires nonempty numerator and denominator arrays and finite epsilon>0. All references must resolve to source planes or previously defined derived planes; cycles are invalid.

### tone

stretch: object keyed by red, green, blue; each channel has kind (asinh or gamma) and parameter (>0).
percentiles: black and white numbers in [0,100], with black < white.
gain and bias: objects with finite red, green, blue values.
saturation: finite number >=0.

All tone fields and all three channels are required at Render readiness. Tone is per output channel, not per source plane.

### psf and execution

psf: enabled (boolean), optional per_plane map. Each per-plane entry supports enabled (boolean), kernel_asset_id (asset reference), max_iterations (integer 1..100), regularization (finite >=0). Enabled processing requires applicable kernel references before execution. Optional common_psf_fwhm_arcsec is finite >0; it does not substitute for a required kernel.

execution: optional fail_fast (boolean), log_file (nonblank string), debug_to_console and debug_to_file (booleans). Runtime policy changes do not alter scene content_revision.

## 7. Assets, thumbnails, renders, and exports

### Asset record

Each assets map key is a nonblank ID unique within the card. Each record requires kind and exactly one of path or uri.

kind is source, discovery_thumbnail, render_image, render_thumbnail, export_image, aligned_planes, footprint, candidate_manifest, provenance, or psf_kernel.
path is a relative path resolved against the card directory; it cannot escape that directory.
uri is an authoritative archive/cache locator; fetching it is a separate action.

Optional members: media_type (MIME string), byte_count (integer >=0), sha256 (64 hexadecimal characters), source_url (HTTP(S)), credit (string).

A discovery_thumbnail requires source_url; credit is retained when available. A generated render_thumbnail is linked through a render record. thumbnail_asset_id must reference a discovery_thumbnail or render_thumbnail. The UI distinguishes their origin. The same immutable source asset may be reused across cards.

### Render record

Each renders entry requires:

- render_id: nonblank ID unique in renders.
- created_at: UTC timestamp.
- content_revision: positive integer, the scene inputs used for this render.
- branch: original or deconvolved.
- image_asset_id: reference to a render_image.
- inputs: snapshot of the effective target, search, selection, canvas, planes, mapping, tone, and psf sections used for this render.
- provenance_asset_id: reference to execution provenance.

Optional members: thumbnail_asset_id (render_thumbnail reference), aligned_plane_asset_ids (array of aligned_planes references), footprint_asset_id (footprint reference).

The inputs snapshot contains the same field vocabulary as the live scene definition, not another project format. It has no renders, exports, or nested history. Referenced assets must remain resolvable within the card. This preserves how older images were made after the working settings change.

Only successful runs are appended to renders. Transient progress and failures are displayed/logged; they are not fabricated successful render records. A successful current preview may become the card thumbnail. Earlier render records and thumbnails remain available as history; a stale generated thumbnail cannot be presented as the current scene result.

### Output choices and export record

output supports format (png or tiff) and destination_directory (nonblank local path). Output dimensions live in canvas only; no duplicate dimensions are stored here. Export requires complete output choices and a matching successful render.

Each exports entry requires export_id (locally unique nonblank string), render_id (existing render reference), created_at (UTC timestamp), format (png or tiff), and destination (the actual output path). Optional asset_id references an export_image when a copy is stored with the card. Export destinations may be outside the associated folder; they are informational and reopening the card does not write to them.

Thumbnails and renders extend the JSON through asset/history records. Binary bytes never go in those records.

## 8. Save and revision rules

1. First save assigns timestamps and content_revision=1; creation can occur before a target is selected.
2. Each accepted change to target, selection, search, canvas geometry, plane activation, mapping, tone, or PSF advances the content revision, including successive unsaved edits. This prevents two different run snapshots sharing a revision. View-only state is excluded.
3. Search-constraint changes affecting discovery advance the revision conservatively. Title, description, discovery provenance, view-only pan/zoom, output destination/format, execution policy, and newly appended artifacts do not invalidate existing render inputs.
4. A render uses a fixed snapshot of its inputs. Editing during processing cannot cause its completed record to claim newer inputs.
5. A save may commit settings and newly completed artifact references together. Required referenced binaries are written completely before publishing their JSON references.
6. Atomic replacement of the JSON is the commit point. Failure retains the previous readable card and its referenced assets. Unreferenced partial artifacts may exist after interruption but must not appear as completed results.
7. Duplicate creates a new scene_id and independent working settings. Generated history may be omitted in the duplicate; the initial duplicate is explicitly shown as a draft until saved. Immutable cached sources may be shared.
8. Unsupported schema versions and unknown fields are rejected with field-specific diagnostics, without rewriting the original document.

## 9. Minimal valid card

```json
{
  "document_type": "galaxy.scene_card",
  "schema_version": 1,
  "scene_id": "24d58958-6d52-47d9-b9ba-2774f81f66f1",
  "title": "Untitled scene",
  "created_at": "2026-09-10T14:00:00Z",
  "updated_at": "2026-09-10T14:00:00Z",
  "content_revision": 1
}
```

This is saveable and reopenable but not searchable or renderable. After naming a target, adding this field remains a valid draft:

```json
{
  "target": {
    "name": "Horsehead Nebula",
    "region": {"kind": "circle", "radius_arcmin": 12}
  }
}
```

The second block is a fragment to merge into the minimal card, not a standalone card. The radius is an illustrative user choice, not a prescribed scientific framing.

## 10. Validation and preliminary limits

Structural checks cover required metadata, types, enumerations, finite numeric bounds, duplicate IDs, paths, and syntactically valid timestamps. Action checks add completeness and referential integrity. Missing binaries are dependency failures, not permission to discard the scene definition or change selected products. A missing thumbnail uses a placeholder; one invalid card must not prevent valid library cards from opening.

Preview currency compares effective inputs/branch with the current content revision; historical settings remain in render.inputs. JSON whitespace and key order are not semantically significant.

The pipeline, CLI, and five-screen UI use JSON scene cards. Galaxy-owned YAML runtime
and temporary translation tooling were retired in Phase 5 after translated examples
and consumer cutover were verified.

## 11. Phase 2 implementation clarifications

- Structural validation allows partial settings, but complete history records must reference assets of the correct kind. Source-specific extracted metadata may contain any JSON value, including null; other supplied null values are rejected.
- Readiness accepts inspected source-plane identifiers and their filter associations as explicit caller context. Product filenames are not invented plane identifiers. Concrete mapping coverage, derived-plane dependencies, and disabled/PSF plane references are checked against that context. Later pipeline integration supplies it after FITS inspection.
- Original and deconvolved readiness are separate; enabled deconvolution requires explicit per-plane policy and kernel references. Missing binary files are separately reported dependencies.
- Save returns the committed card with its updated timestamp. Existing history is append-only; previously registered asset locations and metadata cannot be replaced under the same asset ID. A new render must match its recorded revision and snapshot; a current thumbnail must match the current effective inputs.
- A render snapshot requires selection, canvas, planes, mapping, tone, and psf. Target and search are optional for pinned-product scenes. Execution policy and view-only state do not affect preview currency.
- Duplication starts a new identity and revision, omits generated render/export history, and copies retained local working assets into an independent associated folder. URI-backed immutable cached sources may remain shared. Missing required local copies fail explicitly. Saved/unsaved state is UI state, not a stored lifecycle flag.
- Atomic saves protect against interrupted writes, but concurrent editing of one file by multiple processes is outside this revision's scope.

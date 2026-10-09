# Processing checkpoint specification

Status: normative Phase 2 revision 1, 2026-09-28.

This specification implements CHECKPOINT-001, IDENTITY-001, PROV-001 and
ENCODE-001 from `docs/image_processing_architecture.md`. It defines the aligned
linear checkpoint used by strict `compose-only` execution. It does not define a
general task scheduler, cache eviction policy, or persistence for every numerical
stage.

## 1. Checkpoint set and placement

Each aligned branch is one checkpoint set containing:

- one multi-plane FITS artifact with science arrays, coverage arrays and celestial
  WCS;
- one UTF-8 JSON checkpoint manifest; and
- no mutable success marker outside the manifest.

Legacy flat run directories use these companion names:

| Branch | FITS | Manifest |
| --- | --- | --- |
| `original` | `exported_planes.fits` | `exported_planes.checkpoint.json` |
| `deconvolved` | `exported_planes_deconvolved.fits` | `exported_planes_deconvolved.checkpoint.json` |

New canonical scene-owned placement uses
`renders/r<revision>-<render-id>/<branch>/aligned-planes.fits` and
`.../<branch>/aligned-checkpoint.json`. Existing flat run artifacts remain valid
at their recorded paths and are not moved implicitly.

`src/galaxy/artifact_paths.py` is the single runtime path builder for new branch
outputs and the read-only resolver for those legacy flat paths.

## 2. Canonical JSON and hashes

Canonical serialization is UTF-8 JSON with sorted object keys, no insignificant
whitespace, JSON booleans/null, and finite JSON numbers. Lists retain their
specified order. Paths, timestamps, logging settings and output filenames are not
producer dependencies. A SHA-256 digest is lowercase hexadecimal.

The producer dependency key is SHA-256 over the canonical `producer_inputs`
object. The output integrity digest is SHA-256 over the exact FITS bytes. These
digests answer different questions and are never substituted for one another.

## 3. Revision-one manifest

The root object has exactly these required members:

| Member | Type and meaning |
| --- | --- |
| `document_type` | literal `galaxy.processing_checkpoint` |
| `format_version` | integer `1` |
| `stage_id` | literal `aligned_checkpoint` |
| `domain` | literal `aligned_linear` |
| `branch` | `original` or `deconvolved` |
| `producer_dependency_key` | SHA-256 of canonical `producer_inputs` |
| `producer_inputs` | object defined below |
| `parents` | ordered logical parent IDs |
| `source_content_identities` | ordered source identity/digest records |
| `grid` | common `grid_id`, `[height,width]`, and canonical WCS header mapping |
| `planes` | ordered plane identity/support summary records |
| `stage_order` | ordered stable stage IDs used to produce the checkpoint |
| `algorithm_versions` | map from stable algorithm ID to implementation version |
| `resolved_settings` | resolved upstream settings that affected the arrays |
| `mask_identities` | ordered source validity identities |
| `kernel_identities` | ordered PSF kernel identities; empty for `original` |
| `output` | byte count and SHA-256 for the companion FITS artifact |

Unknown root members fail validation for format version 1.

### 3.1 Producer inputs

`producer_inputs` contains only numerical upstream dependencies:

- `source_content_identities`: stable source ID plus exact source SHA-256, ordered
  by stable source ID;
- `canvas`: resolved center, projection, pixel scale, dimensions, rotation and
  flux-conservation selection;
- `enabled_filters`: sorted filter names that affected ingestion;
- `native_validity`: source content identities and the mask-construction
  algorithm version;
- `native_processing`: branch-specific PSF settings and exact kernel identities;
- `reprojection`: stable algorithm ID and implementation version; and
- `branch`.

Mapping, per-plane display normalization, RGB weights, tone, output format,
thumbnail size, logging and UI state are downstream and excluded. Changing only
those settings therefore permits aligned checkpoint reuse.

The `deconvolved` branch includes resolved per-plane enablement, iteration and
regularization settings, common angular FWHM, and kernel content identities. The
`original` branch uses an empty native-processing object.

### 3.2 Source, mask and kernel identities

A content identity record contains a stable logical ID and SHA-256. A source's
filesystem location and archive retrieval time are diagnostic metadata, not part
of the key. If no authoritative product ID exists, the source ID is the content
digest prefixed with `sha256:`.

Revision one treats the exact source FITS digest plus the declared mask-ingestion
algorithm version as the native validity identity because DQ/WHT/CTX are contained
in the source artifact. External masks or kernels use their own exact digest.

### 3.3 Grid and plane records

Every plane in a checkpoint has the same grid identity. Each plane record contains
`plane_id`, domain, branch, unit or null, ordered source IDs, ordered parent IDs,
valid count, positive-coverage count and shape. Manifest validation compares these
records with the loaded FITS packages before reuse.

## 4. Publication

Orchestration writes the FITS artifact first, calculates its exact digest, writes
the manifest to a sibling temporary file, flushes it, and atomically replaces the
manifest destination. A checkpoint is published only when both final files exist.
Cancellation or failure before manifest replacement leaves no certified reusable
checkpoint. Scene history registers the manifest only after the entire render
succeeds and the normal optimistic-concurrency guard passes.

## 5. Reuse validation

Strict reuse performs these checks in order:

1. manifest exists and parses as revision one;
2. document type, stage, domain and requested branch match;
3. recomputed producer key inside the manifest matches its stored key;
4. canonical requested producer inputs match the stored producer key;
5. companion FITS exists and its byte count and SHA-256 match `output`;
6. FITS packages load under IMG-CONTRACT-001;
7. loaded plane order, IDs, branch, shape, grid, lineage and support summaries
   match `planes`; and
8. scene readiness accepts the inspected planes and requested branch.

Every failure is actionable and names the failed class: missing manifest,
unsupported format, producer mismatch, missing artifact, integrity mismatch,
geometry/plane mismatch, or readiness mismatch. Renaming both files does not alter
numerical compatibility because filenames are excluded; the manifest must be
explicitly paired with the selected FITS path.

## 6. Execution modes and legacy import

`compose-only` is strict. It never constructs reprojections, masks, deconvolution
or an inferred manifest. A missing or incompatible checkpoint fails and directs
the caller to run full or reprojection-only processing.

Full and reprojection-only execution may build a new checkpoint in a new run
directory. They do not overwrite a registered historical run.

`load_multiplane_records` is the explicit inspection adapter for a legacy FITS
stack. It may display arrays and recover stored coverage/WCS, but absence of a
revision-one manifest means the stack is uncertified and cannot satisfy strict
compose-only reuse. Missing coverage is not promoted to certified all-valid
support. A later user-authorized import workflow may persist assumptions, but no
such workflow is introduced in Phase 2 revision one.

## 7. Shared rendering and output identity

Scene rendering and direct aligned-stack preview call the same composition and
tone numerical function. Each entry point supplies an explicit mapping/tone preset;
equal packages and equal settings produce equal floating RGB results. Direct
inspection of an uncertified legacy stack remains allowed and is labeled as such.

Every successful branch registers separate roles for preview PNG, high-depth TIFF,
thumbnail, aligned FITS and checkpoint manifest. External export requires an
explicit branch and format. PNG selects that branch's preview role; TIFF selects
that branch's high-depth TIFF role. A missing matching role fails without
re-encoding another artifact.

## 8. Version policy

Algorithm versions are stable constants owned by the implementing modules. They
change whenever code can change numerical output or mask/identity interpretation.
Application marketing/version strings, timestamps and source checkout paths are
not algorithm versions. Revision-one identifiers are:

- `fits-validity-v1`;
- `masked-rl-v1`;
- `reproject-interpolation-v1`;
- `reproject-adaptive-flux-v1`;
- `aligned-fits-v1`; and
- `checkpoint-manifest-v1`.

## 9. Acceptance matrix

Automated verification shall cover:

- tone/mapping changes reuse the aligned checkpoint;
- source bytes, canvas, mask algorithm, native PSF setting/kernel, branch or
  reprojection algorithm changes reject reuse;
- corrupt/missing FITS and manifest artifacts reject reuse;
- a self-inconsistent producer key rejects reuse;
- renamed explicitly paired files remain valid;
- incompatible grids or plane summaries reject reuse;
- legacy FITS remains inspectable but strict reuse rejects it;
- scene and direct entry points are numerically equal for equal settings and
  partial support;
- branch-specific PNG/TIFF export selects the registered role;
- the TIFF path contains uint16 RGB data with more than 256 distinct levels; and
- cancellation cannot publish a successful checkpoint asset or render record.

## Bridge integration amendment (2026-10-07)

New certified checkpoints use format version 2 and BRIDGE-WIRE-002 in
[the bridge algorithm](reprojection_bridge_algorithm.md). It supersedes the
version-1 producer/support shorthand above. Both On and Off require explicit
SUPVER support extensions, complete support counts/hashes, and bridge
configuration/profile/version in producer identity. Old files remain inspectable;
format-1 checkpoints cannot certify current compose-only execution. Regenerate
with full/reprojection-only processing. New aligned value files preserve bridge
diagnostics, observational validity/coverage, presentation coverage, influence,
WCS, units and lineage as a single checksummed artifact package.

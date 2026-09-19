# Artifact Storage Specification — Revision 1

## 1. Authority and scope

This document is the normative storage and naming contract for Galaxy scene cards,
acquired source products, processing artifacts, previews, and retained exports. It
defines where durable data belongs and how a scene card refers to it. The
[scene-card schema](scene_card_schema.md) defines JSON structure and validation;
this specification defines filesystem layout.

The contract applies to newly created artifacts. Existing artifacts are not
silently moved or renamed; migration requires an explicit, verified operation.

## 2. Storage domains

Galaxy uses three storage domains with different ownership and lifetime rules.

1. **Scene library:** the effective `scene_directory` contains scene-card JSON
   documents and their associated asset roots. This is durable user data.
2. **Application cache:** `<scene-directory>/.galaxy-cache/` contains reusable,
   regenerable archive downloads and discovery results. Cache contents are not
   part of a portable scene and may be removed without altering the scene card.
3. **External exports:** a user-selected destination may be outside the scene
   directory. The scene card records that destination as history, but reopening a
   card never writes to it.

The default scene directory remains `<project-root>/artifacts/scenes`. Application
configuration and command-line precedence are defined by REQ-CONFIG-001 through
REQ-CONFIG-010.

## 3. Canonical scene names

A default scene key shall have this form:

```text
<title-slug>-<scene-id-prefix>
```

- `title-slug` is the lowercase title with each run of characters outside
  `a-z`, `0-9` replaced by one hyphen, with leading and trailing hyphens removed.
- An empty result becomes `untitled-scene`.
- `title-slug` is truncated to 64 characters before trailing hyphens are removed.
- `scene-id-prefix` is the first eight lowercase hexadecimal characters of the
  canonical scene UUID, without hyphens.
- The default card filename is `<scene-key>.scene.json`.
- The associated asset root is `<scene-key>.assets/`.

The display title is independent of the scene key. Renaming a title shall not
rename an existing card or asset root. An explicitly selected card filename is
permitted. For a canonical `<scene-key>.scene.json` card, the asset root remains
`<scene-key>.assets/`. For an explicitly named `<name>.json` card that does not use
the `.scene.json` suffix, its associated asset root shall be the matching `<name>/`
sibling directory. For example, `Pillars.json` owns `Pillars/`. The explicit name
shall be a safe filesystem component, but it is not rewritten or case-normalized.
This exception permits deliberate human-facing example names without changing the
canonical naming rule used for automatically created cards.

## 4. Canonical directory layout

```text
<scene-directory>/
    .galaxy-cache/
        candidates/
            <search-key>.candidates.json
        archive/
            <identity-hash[0:2]>/
                <identity-hash>/
                    <archive-basename>

    <scene-key>.scene.json
    <scene-key>.assets/
        inputs/
            discovery/
                <asset-id>.<ext>
            psf/
                <asset-id>.fits
            sources/
                <identity-hash>/
                    <archive-basename>
        renders/
            r<revision>-<render-id>/
                candidates.json
                downloads.json
                provenance.json
                footprints.png
                original/
                    aligned/
                        <plane-key>.fits
                        <plane-key>.coverage.fits
                    aligned-planes.fits
                    composite.png
                    composite.tiff
                    thumbnail.png
                deconvolved/
                    aligned/
                        <plane-key>.fits
                        <plane-key>.coverage.fits
                    aligned-planes.fits
                    composite.png
                    composite.tiff
                    thumbnail.png
        exports/
            <export-id>/
                <export-basename>.png
                <export-basename>.tiff
```

Optional files and directories are created only when their corresponding data
exists. The `deconvolved/` branch exists only when PSF processing succeeds. A
retained export copy is optional because the authoritative export may be external.

## 5. Name derivation

### 5.1 Stable identifiers

Scene-card `asset_id`, `render_id`, `export_id`, and authoritative archive product
identities are the logical identifiers. A filename shall never be used as a
substitute for one of those identities.

`render-id` and `export-id` in directory names shall be the exact identifiers from
the scene card. `revision` shall be the decimal render input revision padded to at
least six digits, for example `r000012-<render-id>`.

### 5.2 Archive identity hash

`identity-hash` shall be the lowercase 64-character SHA-256 hexadecimal digest of
the UTF-8 authoritative product identity. When `data_uri` exists it is the hash
input; otherwise `product_id` is the hash input. The selected input and resulting
digest shall be recorded in the download manifest.

`archive-basename` is the terminal filename supplied by the authoritative archive.
Path components supplied by a remote system are discarded. If the basename is
missing or unsafe, use `source.fits` while retaining the authoritative identity in
metadata. Identity hashes prevent collisions between equal basenames.

### 5.3 Plane and user-supplied names

`plane-key`, `asset-id`, and retained `export-basename` components shall be made
filesystem-safe without changing their logical identifiers in JSON. A safe
component:

- contains only lowercase `a-z`, digits, period, underscore, and hyphen;
- begins with a letter or digit;
- is not `.` or `..` and is not a reserved Windows device name;
- contains no path separator, drive prefix, control character, or trailing period
  or space; and
- is no longer than 120 characters, using a stable identity-hash suffix when
  truncation or collision resolution is required.

## 6. Placement by artifact kind

| Scene asset kind | Required durable placement |
| --- | --- |
| `source` | `inputs/sources/<identity-hash>/<archive-basename>`, when materialized as a portable scene-owned file; otherwise retain its authoritative URI and resolve it through the application cache. |
| `discovery_thumbnail` | `inputs/discovery/<asset-id>.<ext>` when copied locally; a remote attributed thumbnail may remain URI-backed. |
| `psf_kernel` | `inputs/psf/<asset-id>.fits`. |
| `candidate_manifest` | `inputs/discovery/candidates.json` for the accepted pre-render discovery snapshot; each successful render freezes its execution copy at `renders/r<revision>-<render-id>/candidates.json`. |
| `provenance` | `renders/r<revision>-<render-id>/provenance.json`. |
| `footprint` | `renders/r<revision>-<render-id>/footprints.png`. |
| `aligned_planes` | The applicable branch's `aligned-planes.fits`. Individual aligned planes and coverage arrays belong below that branch's `aligned/` directory. |
| `render_image` | The applicable branch's `composite.png`, `composite.tiff`, or `thumbnail.png`. |
| `render_thumbnail` | The applicable branch's `thumbnail.png`. |
| `export_image` | `exports/<export-id>/<export-basename>.<format>` only when the scene retains a managed copy. |

`downloads.json` is the deterministic acquisition manifest for the run. It records
the selected product identity, authoritative URI, archive basename, cache or local
source location, checksum, byte count, and retrieval outcome. It is distinct from
`candidates.json`, which records discovery and selection decisions.

## 7. Scene-card references

- Every scene-owned `assets.*.path` shall use `/` separators and be relative to the
  directory containing the scene card.
- A local asset path shall begin with the associated asset-root name determined in
  section 3 and resolve within that root after normalization and symbolic-link
  resolution.
- `..`, absolute paths, drive-relative paths, URI text in `path`, and links that
  escape the asset root are invalid.
- URI-backed assets shall use `uri`; they shall not pretend that an application
  cache entry is a portable relative path.
- Every path referenced by a successful render or retained export record shall
  exist, match its recorded byte count and SHA-256 digest, and have the artifact
  kind required by the scene-card schema before the record is committed.
- Application-cache paths shall not be persisted in scene-card `path` fields.

Moving a scene card together with its associated asset-root sibling preserves all
scene-owned references. Moving only the JSON document may leave dependency issues,
which shall be reported without silently substituting files.

## 8. Cache layout and behavior

`<scene-directory>/.galaxy-cache/candidates/` stores discovery manifests using a
lowercase SHA-256 `search-key` derived from canonical JSON discovery inputs.

`<scene-directory>/.galaxy-cache/archive/` stores exact downloaded bytes by
authoritative identity hash. The cache may maintain indexes, locks, partial files,
or metadata sidecars below `.galaxy-cache/`, but those implementation files are not
scene artifacts and shall not be referenced by relative scene paths.

An archive cache hit is valid only after identity, expected byte count when known,
and recorded SHA-256 are verified. A cache implementation shall not overwrite
different bytes at an existing completed identity path.

## 9. Lifecycle and write rules

- Downloaded source bytes and committed render directories are immutable.
- A rerender always receives a new `render_id` and directory, even when it uses the
  same content revision.
- Writers shall build files under a uniquely named incomplete sibling, verify all
  required artifacts, then atomically publish the completed directory or files.
- Incomplete work shall not be referenced by a successful render record.
- Failed or cancelled runs may retain diagnostic temporary data, but it shall be
  clearly marked incomplete and shall not occupy a canonical render directory.
- Scene-card history is appended only after the corresponding immutable artifacts
  have been published successfully.
- Deleting cache data shall not delete scene-owned inputs, renders, or exports.
- User-directed deletion of a scene shall treat its JSON card and matching asset
  root as one recoverable unit.

## 10. External export rules

The user-selected PNG or TIFF is a delivery artifact, not the source of render
truth. Its destination may be outside the scene directory. The export record stores
the actual destination and the matching `render_id`; it may also reference a
scene-owned `export_image` copy. Reopening a scene shall never recreate, overwrite,
or modify an external export automatically.

## 11. Example

For scene `horsehead-nebula-12345678.scene.json`, revision 12, and render ID
`7aa8c6e0-6023-4a4d-8c8d-d2241cdd32c4`, the original composite is:

```text
horsehead-nebula-12345678.assets/renders/
    r000012-7aa8c6e0-6023-4a4d-8c8d-d2241cdd32c4/
        original/composite.tiff
```

The corresponding scene-card asset path is the same path expressed relative to
the scene-card directory with `/` separators.

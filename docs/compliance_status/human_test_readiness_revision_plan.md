# Bundled Example Human-Test Readiness Revision Plan

Date: 2026-09-15.
Status: implementation and automated entry verification complete; manual
`AC-HUMAN-001` signoff pending.

## 1. Objective

Prepare one bounded, deterministic human acceptance flow:

```text
Normal UI launch
    -> Saved scenes / project selector
    -> select Pillars of Creation
    -> open Pillars.json safely
    -> inspect the scene's selected and generated artifact inventory
```

This first flow shall not require network access, FITS downloads, reprojection, or
rendering. Its purpose is to establish that a bundled example can be found, loaded,
understood, and copied safely before testing processing behavior.

## 2. Baseline

- `artifacts/Pillars.json` is a valid, versioned scene card with six exact MAST
  product pins and no local asset dependencies.
- Other content below `artifacts/`, including a local `Pillars/` folder, is ignored
  and shall not be required by the test.
- The configured user scene library defaults to `artifacts/scenes`.
- The Saved scenes screen currently scans only the configured user scene directory,
  so it does not find the bundled card during a normal launch.
- Generic workspace discovery can expose scene-card paths, but it is not the intended
  project-selector experience.
- The current UI reports thumbnail, readiness, and missing dependencies in the
  library but has no consolidated artifact inventory after opening a scene.
- A normally opened saved scene is writable at its source path; a bundled example
  therefore needs explicit read-only or copy-on-save semantics.

The open storage-layout implementation gap `GAP-STORAGE-001` does not block this
read-only first flow. It must be closed before a later human flow creates canonical
render artifacts.

## 3. Phase 8A — acceptance contract

Update [design requirements](../design_requirements.md), [user
flows](../user_flows.md), and [UI acceptance
coverage](../testing/ui_scene_coverage.md) with atomic requirements for:

1. discovering versioned bundled example scene cards independently of the user
   scene directory;
2. labeling bundled examples separately from user scenes;
3. opening a bundled example without allowing an ordinary save to overwrite it;
4. saving changes to an example only as a new user-owned scene;
5. displaying a deterministic artifact inventory derived from the scene card and
   verified referenced files; and
6. distinguishing remote-only sources, available local assets, missing references,
   corrupt references, current renders, stale renders, and external export history.

Define `AC-HUMAN-001` as the first manual acceptance case. Do not infer new behavior
from UI convenience; requirements and acceptance assertions are written before code.

## 4. Phase 8B — example-library and inventory domain layer

Add UI-independent, typed behavior under `src/galaxy/`:

- Discover bundled examples from the project distribution's `artifacts/*.json`
  files, accepting only valid `galaxy.scene_card` documents.
- Continue discovering user scenes only from the configured `scene_directory`.
- Extend library entries with an explicit origin such as `bundled_example` or
  `user_scene`; do not infer ownership from title or filename casing.
- Deduplicate entries by resolved path and stable `scene_id` without hiding invalid
  user entries.
- Open a bundled example as a protected source. Preserve its scene definition for
  inspection, but route a subsequent save to a new default user-scene path and new
  scene identity.
- Introduce immutable artifact-inventory records for selected sources, local source
  assets, discovery manifests, aligned planes, render branches, thumbnails,
  footprints, provenance, and export history.
- Derive inventory only from scene-card records plus filesystem verification through
  existing asset path, byte-count, and SHA-256 checks. Do not treat arbitrary files
  in an unreferenced same-name directory as scene artifacts.

For the committed Pillars card, the expected inventory is:

| Category | Expected count/state |
| --- | --- |
| Selected source products | 6 |
| Remote-only downloadable sources | 6 |
| Available local source assets | 0 |
| Candidate-manifest assets | 0 |
| Aligned-plane sets | 0 |
| Successful renders | 0 |
| Exports | 0 |
| Missing or corrupt referenced assets | 0 |

## 5. Phase 8C — project selector and artifact UI

Revise the Saved scenes screen into a project selector with two clearly labeled
groups:

- **Examples**, containing Pillars of Creation;
- **Saved scenes**, containing user-owned cards from the configured scene directory.

Each entry shall show title, target, origin, readiness, save timestamp, and thumbnail
or placeholder. Opening Pillars shall navigate to Scene refinement and display a
visible example/protected marker.

Add an **Artifacts** panel to Scene refinement. It shall summarize category counts
and provide a row for every selected source showing mission, filter, processing
level, authoritative product identity, filename, and status. Generated-artifact
rows shall identify branch, revision, current/stale state, and verified path when
present. Empty categories shall say `None created` rather than disappearing.

The Save action for an example shall be labeled `Save as new scene` and shall never
target `artifacts/Pillars.json`.

## 6. Phase 8D — automated verification

Add deterministic tests before enabling the human check:

1. Normal launch lists Pillars under Examples without `--scene-dir artifacts`.
2. The configured user library remains independent and does not absorb unrelated
   JSON or generated artifact files.
3. Selecting Pillars opens Scene refinement with the expected title, target, six
   filters, and six exact MAST identities.
4. Artifact inventory reports six remote-only sources and zeros for every generated
   category.
5. The flow passes when the ignored local `artifacts/Pillars/` directory is absent.
6. Unreferenced files under a same-name directory do not appear in inventory.
7. Missing and corrupt referenced assets receive distinct statuses.
8. Current and stale render records are distinguished deterministically.
9. Saving an edited example creates an independent card under the configured scene
   directory and leaves the bundled JSON byte-for-byte unchanged.
10. Windows case-insensitive paths do not create duplicate `pillars` and `Pillars`
    entries.

Run focused domain and Streamlit tests, the full offline suite, syntax validation,
dependency checks, documentation-link checks, and `git diff --check`.

## 7. Phase 8E — operator documentation and cleanup

- Update `README.md` with the normal UI launch command and first-flow instructions.
- Remove or correct statements that describe the UI as preview-only or instruct the
  user to override the scene directory merely to see the bundled example.
- Update the UI and pipeline traceability matrices with actual implementation and
  test names.
- Label historical phase documents clearly enough that their superseded open-gap
  text cannot be mistaken for current status.
- Test from a clean scene directory and without the ignored local Pillars folder.
- Close `GAP-HUMAN-001` only when automated entry criteria pass. Retain
  `GAP-STORAGE-001` until artifact producers and consumers implement the canonical
  storage layout.

## 8. Human acceptance procedure — AC-HUMAN-001

### Preconditions

- Use a clean checkout containing tracked `artifacts/Pillars.json` but no
  `artifacts/Pillars/` directory.
- Use an empty configured user scene directory.
- Disable or disconnect network access to prove the flow is local.
- Record the Git revision and SHA-256 of `Pillars.json`.

### Procedure

1. Launch the Streamlit UI with no input-path or scene-directory override.
2. Open the Saved scenes / project selector.
3. Confirm Pillars of Creation appears once under Examples and the user scene group
   is empty.
4. Confirm the entry is labeled as an example, render-ready, and has a placeholder
   rather than a claimed generated thumbnail.
5. Open Pillars and confirm navigation to Scene refinement.
6. Inspect the Artifact panel and confirm the expected inventory table from Phase
   8B, including the six filters and remote-only status.
7. Change the title and one tone value, then choose `Save as new scene`.
8. Confirm a new independently editable scene appears under Saved scenes.
9. Confirm the original Pillars card remains under Examples and its recorded hash is
   unchanged.

### Exit criteria

- Every procedure step passes without network access or manual file placement.
- No warning reports a missing artifact for the standalone Pillars card.
- The example is not modified, duplicated in the selector, or treated as user-owned.
- The new user-owned copy reopens with the edited values.
- Any failure is recorded with the step, observed state, expected state, logs, and
  screenshot before remediation begins.

## 9. Out of scope for this first human flow

- downloading the six pinned FITS products;
- checking download size, cache reuse, or archive availability;
- WCS registration, reprojection, PSF processing, RGB composition, or export;
- visual-quality or astrometric-accuracy judgments; and
- canonical render-directory creation under `GAP-STORAGE-001`.

Those behaviors belong to subsequent human flows after this selector and inventory
baseline is accepted.

## 10. Execution record

Phases 8A through 8E were executed in sequence on 2026-09-15. The implementation
uses `LibraryOrigin`, `list_project_library`, `inspect_scene_artifacts`,
`save_example_as_user_scene`, the origin-aware project selector, and the Refinement
Artifacts panel. The final focused UI suite passed 25 tests. The complete offline
suite passed 206 tests with the one live archive integration test skipped by its
documented opt-in guard. Syntax compilation, 279 JSON documents, 238 unique
requirement definitions, documentation links, ignore behavior, and whitespace
checks passed. These results are the automated entry evidence for the manual
procedure.

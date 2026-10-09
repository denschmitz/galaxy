# Galaxy User Flows

Status: target specification; the Phase 4 screen shell is implemented, with retained
acceptance gaps tracked in docs/compliance_status/known_gaps.md.
Normative behavior: [Design requirements](design_requirements.md).
Persistence: [Scene card storage schema](scene_card_schema.md).

## Navigation and shared behavior

Startup loads project-root `galaxy.config.json`, creating it with `scene_directory: artifacts/scenes` when absent. The effective scene directory follows command-line override, configuration, then default precedence (REQ-CONFIG-001 through REQ-CONFIG-010; REQ-CLI-004). Saved scenes lists this library; new scene saves default to it. Configuration failures are reported before normal screen entry.

Normal launch opens Discovery. Explicit scene card or manifest input opens Refinement; explicit aligned-plane input opens Render. A workdir follows its resolved artifact. Opening an artifact does not save a scene card automatically.

Main path: Discovery -> Refinement -> Render and adjust -> Output and save.
Resume path: Discovery -> Saved scenes -> Refinement.
Render can return to Refinement, and Output can return to Render.

Navigation within an active scene retains edits. Replacing or closing an unsaved scene offers Save, Discard, and Cancel; a failed save keeps the scene open. Loading, empty results, errors, cancellation, and stale previews are states within these five screens. Logical regions below do not prescribe pixel layouts.

## UF-01 Discovery

**Purpose:** Find a scene by browsing, name, or sky region.
**Entry:** Normal launch or navigation back to Discovery.
**Regions:** Name/identifier search; coordinates and region input; thumbnail gallery; source status; Saved scenes entry.

1. User browses tracker thumbnails, submits a name, or supplies coordinates and region dimensions.
2. System shows discovery hints or name matches; ambiguous names require a target choice.
3. User selects a result.
4. System opens an unsaved scene card draft in Refinement with target inputs and source attribution.

**Alternatives:** Loading identifies the source. No matches is distinct from a failed request. Invalid coordinates show field errors. A failed tracker leaves name and coordinate search available. Missing images use selectable placeholders. Returning from Refinement restores query, filters, and scroll position. A name match makes no promise of archive imaging coverage.

**Exit:** UF-02 or UF-05.
**Requirements:** REQ-FIND-001 through REQ-FIND-008; REQ-NAV-001; REQ-DISC-001 through REQ-DISC-008; REQ-IFACE-001; REQ-SOURCE-001 through REQ-SOURCE-004.

## UF-02 Scene refinement

**Purpose:** Choose observations, filters, initial color mapping, and crop.
**Entry:** Discovery selection, opened scene card/manifest, or reopened scene card.
**Regions:** Title/target; Data; Artifacts; Color; Frame; Save scene; Render.

1. System queries observations then products, or restores saved explicit product selections.
2. System displays a verified artifact inventory, including remote-only selected products and explicit empty generated-artifact categories.
3. System consolidates duplicate downloadable product identities and associates the persisted candidate manifest with the active draft.
4. System displays the proposed selection mode, mission scope, unique-product/filter counts, instruments, missions, and estimated download size.
5. User chooses a bounded preview, one recommended product per filter, or a custom selection and may constrain the proposal to HST or JWST.
6. System displays one recommended product per candidate group with a concise explanation; alternatives remain available through grouped disclosure.
7. User applies the recommendation or selects observations, products, and filters manually.
8. System proposes RGB contributions using the configured mapping strategy; user applies or edits them.
9. System displays the existing canvas or a provisional canvas derived from the resolved target and search region.
10. After the selected FITS products are locally inspectable, System proposes a tight canvas enclosing their measured footprint union and displays its dimensions, scale, orientation, and geometric warnings.
11. For a new scene's first render, System applies a warning-free fitted canvas; for later changes, User explicitly invokes `Fit selected scans` or retains the current frame.
12. User optionally adjusts frame center, dimensions, rotation, and pixel scale against available footprints.
13. Applying a selection with recommended defaults reconciles mapping and
    selection-dependent processing to exactly the selected filters while preserving
    valid local source references and the accepted canvas.
14. User saves a draft or proceeds to Render when validation passes. A bundled example is first materialized as a user copy and all work is performed on that copy.

**Alternatives:** No usable images, query failure, and incomplete retrieval have distinct messages. Conflicting normalized metadata is labeled conflicting and unknown metadata is labeled unknown. Products remain inspectable under their observation identity. Missing region dimensions require input before provisional framing. Missing or invalid FITS WCS blocks automatic fit and identifies the affected product. Disconnected, low-fill, widely separated, or excessively large footprint unions show a warning with measurable geometry and let the user revise the selection, continue, or keep the current frame. An infeasible single TAN projection requires separate scenes or a revised selection. Changing data rechecks mapping references, retains an accepted user frame, and identifies selected footprints outside it. Invalid mappings block rendering. Footprints do not guarantee full pixel coverage. Incomplete settings can be saved as a draft with its candidate-manifest reference. Before a selection is applied, readiness guidance uses workflow actions; schema field paths remain available only as technical details.

**Exit:** UF-03 or UF-01; draft save stays here.
**Requirements:** REQ-REFINE-001 through REQ-REFINE-040; REQ-WCS-009 through REQ-WCS-016; REQ-SELECT-001 through REQ-SELECT-015; REQ-MAN-004 through REQ-MAN-006; REQ-DATA-010 through REQ-DATA-011; REQ-ART-001 through REQ-ART-005; REQ-UI-004; REQ-IFACE-002 through REQ-IFACE-005.

## UF-03 Render and adjust

**Purpose:** Inspect and improve the image.
**Entry:** Validated refinement, return from Output, or explicit aligned-plane input.
**Regions:** Preview; stage progress/cancel; mapping/tone controls; output-footprint
and brightness-reference controls; normalization proposal; background pedestal
controls and region overlay; branch selector when applicable; Refinement; Save draft;
Output.

1. User requests a preview.
2. System retrieves missing selected data and runs applicable processing stages with progress.
3. System displays the completed preview associated with the scene content revision and branch.
4. User independently selects the output footprint and the pixels used to derive
   the tone transform. The recommended new-scene setting retains the union of valid
   input pixels while deriving brightness percentiles from pixels where all required
   bands overlap.
5. System applies the one derived tone transform to the full output footprint. It
   does not brighten partial-coverage pixels according to contributor count.
6. User selects independent-channel or shared-intensity tone, chooses linear,
   asinh, gamma, or GHS, adjusts only the applicable parameters, and explicitly
   selects clipping or rescaling when shared tone can exceed gamut.
7. User may request a deterministic auto-stretch proposal from the persisted
   background regions, inspect its confidence and clipping diagnostics, preview it,
   and explicitly Apply or Recompute it. Reopening uses the applied numerical
   values without re-estimation.
8. User may explicitly select the single-main-stretch preset, which changes plane
   stretches to linear and selects shared-intensity tone; existing recipes are not
   changed silently.
9. User may preview and apply a branch-specific normalization proposal. Preview
   does not alter the scene; Apply persists resolved values and marks the prior
   render out of date.
10. User may enable pedestal correction, enter one or more ICRS sky rectangles and
   optional exclusion rectangles, and request Background Preview.
11. System displays the region overlay, common-sample diagnostics, resolved
   per-plane proposal, and a candidate corrected render without changing the scene.
12. User applies the branch-specific proposal, adjusts mapping/tone, disables the
   correction, or revises the regions. Apply persists resolved values and marks the
   prior render out of date; disable returns to exact off-mode behavior.
13. User requests another canonical preview and continues to Output.

**Alternatives:** Unrendered, running, cancellation requested, cancelled, failed, current, and out-of-date preview states. Cancellation completes at a safe stage boundary. Failure/cancellation retains the previous successful image. Scene edits mark earlier previews out of date. Data/crop changes return through Refinement. Explicit aligned-plane inputs may be previewed without inventing absent provenance; saving a draft remains possible while missing scene inputs prevent full pipeline readiness. Successful renders extend the scene card with asset references and input snapshots; earlier render history remains available.

**Exit:** UF-02 or UF-04; draft save stays here.
**Requirements:** REQ-RENDER-001 through REQ-RENDER-009; REQ-UI-002 and REQ-UI-003; REQ-PROJ-019; REQ-NAV-003 through REQ-NAV-007; REQ-BG-001 through REQ-BG-008; REQ-COV-001 through REQ-COV-008; REQ-NORM-009 through REQ-NORM-014; REQ-TONE-001 through REQ-TONE-013.

## UF-04 Output and save

**Purpose:** Export an image and save a reusable scene.
**Entry:** Render workspace.
**Regions:** Format/dimensions/destination; scene title/thumbnail; separate Save scene and Export controls and statuses.

1. User chooses PNG or TIFF, dimensions, and destination.
2. System preserves the sky frame when resolution changes and identifies any required rerender.
3. User requests a matching render if needed.
4. User names and saves the scene with applicable thumbnail and pinned selected products.
5. User exports the matching successful image.

Save and export may occur in either order. Saving does not require a successful export.

**Alternatives:** Invalid dimensions, existing-file overwrite confirmation, out-of-date render, invalid destination, save failure, and export failure. Incompatible aspect ratios require a frame change in Refinement. Save failure leaves the prior saved scene readable. A current preview supplies the thumbnail; otherwise use an attributed discovery image or placeholder.

**Exit:** UF-03, UF-05, or UF-01 with unsaved-edit handling.
**Requirements:** REQ-SAVE-001 through REQ-SAVE-009; REQ-CARD-001 through REQ-CARD-012; REQ-OUT-001.

## UF-05 Saved scenes

**Purpose:** Materialize a bundled example as user-owned work, or resume, duplicate, or delete a stored user scene.
**Entry:** Saved scenes navigation from Discovery or after saving.
**Regions:** Examples; Saved scenes; cards with inline-editable user-scene title,
target, origin, thumbnail kind, derived readiness, saved time;
Open/Duplicate/Delete; title Commit/Cancel; deletion confirmation; Discovery.

1. System lists registered bundled examples separately from user-owned locally stored cards.
2. For a user-owned scene, Open restores it in Refinement and Duplicate creates an
   independently editable scene with a new identifier. Its display title adds
   ` copy`; its JSON and asset-root names use the source title slug plus the new
   identifier without adding the generated `copy` label.
3. For a bundled example, Open opens the existing same-name user copy or atomically creates that copy first when it is absent.
4. Duplicate on a bundled example creates the same-name user copy; if its JSON already exists, the system requests overwrite confirmation and preserves the existing paired binary asset folder regardless of the choice.
5. The example entry uses a valid thumbnail referenced by the user copy when available and otherwise displays a placeholder.
6. Delete on a user-owned scene identifies the exact scene-card path and associated asset root, then waits for explicit confirmation.
7. Confirmed deletion moves that pair as one recoverable unit, refreshes Saved scenes, and closes the scene when it was active.
8. User activates a user-scene title in place, edits the prefilled single-line
   input, and commits or cancels without leaving Saved scenes. A committed title
   changes display metadata only and does not rename storage.
9. User inspects selected and generated artifact status, continues refinement, and saves only to the user copy.

**Alternatives:** An empty user library still displays bundled examples. Declining an example overwrite leaves both the user JSON and paired asset folder unchanged. Delete is unavailable for bundled examples and while an associated operation is running. Cancelling deletion changes nothing. A failed deletion restores any moved member, reports failure, retains an active scene, and refreshes the library from disk. Application cache entries, external exports, and other projects are outside deletion scope. An invalid existing user copy is reported rather than silently replaced by Open. Missing thumbnails use placeholders. Missing referenced binary assets are identified without losing the scene definition. Missing cached data remains remote-only and may be downloaded using pinned identities; unavailable products require user selection changes, without silent substitution. Equivalent case-insensitive paths are not listed twice.

**Exit:** UF-02 or UF-01.
**Requirements:** REQ-LIB-001 through REQ-LIB-034; REQ-ART-001 through REQ-ART-005; REQ-CARD-004 through REQ-CARD-007.

## NaN bridge workflow (implemented, 2026-10-08)

In Scene refinement, "Bridge small NaN holes" is a saved On/Off switch defaulting
On for absent settings. Generate preview saves the draft, locks the switch during
the render, and automatically prepares eligible native presentation holes after
FITS/mask loading. Native observational data remains intact. Off uses strict
missing-data handling. Changing the switch marks older results stale and requires
full/reproject-only processing; compose-only rejects incompatible checkpoints.
Save, reopen and duplicate preserve explicit states. Help explains that estimates
are for presentation and that rejected holes remain invalid.
Requirements: REQ-BRIDGE-001..021.

After changing this switch, use Render and adjust > Generate preview. That action
saves the draft and runs fresh reprojection; a preview PNG is sufficient for
inspection. A final TIFF is optional. Old checkpoints and historical renders
without an explicit bridge snapshot cannot certify the current settings. Export
rejects a stale preview until a matching successful render exists.

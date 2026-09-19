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
**Regions:** Title/target; Data; Artifacts; Color; Frame; Save draft or Save as new scene; Render.

1. System queries observations then products, or restores saved explicit product selections.
2. System displays a verified artifact inventory, including remote-only selected products and explicit empty generated-artifact categories.
3. User compares observation identity, date, instrument, filters, exposure, coverage, and local availability.
4. System displays candidate/filter recommendations based on the configured selection policy.
5. User applies the recommendation or selects observations, products, and filters manually.
6. System proposes RGB contributions using the configured mapping strategy; user applies or edits them.
7. System displays the existing canvas or initializes the default from the resolved target and search region.
8. User optionally adjusts frame center, dimensions, rotation, and pixel scale against available footprints.
9. User saves a draft or proceeds to Render when validation passes. A bundled example saves only as a new user-owned scene.

**Alternatives:** No usable images, query failure, and incomplete retrieval have distinct messages. Unknown metadata is labeled unknown. Products remain inspectable under their observation identity. Missing region dimensions require input before default framing. Changing data rechecks mapping references and retains the user frame. Invalid mappings block rendering. Footprints do not guarantee full pixel coverage. Incomplete settings can be saved as a draft.

**Exit:** UF-03 or UF-01; draft save stays here.
**Requirements:** REQ-REFINE-001 through REQ-REFINE-018; REQ-SELECT-001 through REQ-SELECT-005; REQ-ART-001 through REQ-ART-005; REQ-UI-004; REQ-IFACE-002 through REQ-IFACE-005.

## UF-03 Render and adjust

**Purpose:** Inspect and improve the image.
**Entry:** Validated refinement, return from Output, or explicit aligned-plane input.
**Regions:** Preview; stage progress/cancel; mapping/tone controls; branch selector when applicable; Refinement; Save draft; Output.

1. User requests a preview.
2. System retrieves missing selected data and runs applicable processing stages with progress.
3. System displays the completed preview associated with the scene content revision and branch.
4. User adjusts mapping or tone and requests another preview.
5. User continues to Output.

**Alternatives:** Unrendered, running, cancellation requested, cancelled, failed, current, and out-of-date preview states. Cancellation completes at a safe stage boundary. Failure/cancellation retains the previous successful image. Scene edits mark earlier previews out of date. Data/crop changes return through Refinement. Explicit aligned-plane inputs may be previewed without inventing absent provenance; saving a draft remains possible while missing scene inputs prevent full pipeline readiness. Successful renders extend the scene card with asset references and input snapshots; earlier render history remains available.

**Exit:** UF-02 or UF-04; draft save stays here.
**Requirements:** REQ-RENDER-001 through REQ-RENDER-009; REQ-UI-002 and REQ-UI-003; REQ-PROJ-019; REQ-NAV-003 through REQ-NAV-007.

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

**Purpose:** Open a bundled example or resume or duplicate stored work.
**Entry:** Saved scenes navigation from Discovery or after saving.
**Regions:** Examples; Saved scenes; cards with title, target, origin, thumbnail kind, derived readiness, saved time; Open/Duplicate; Discovery.

1. System lists registered bundled examples separately from user-owned locally stored cards.
2. User chooses Open, Duplicate, or Save as new scene as applicable to the entry origin.
3. Open restores the scene in Refinement. A bundled example is visibly protected; Duplicate creates an independently editable unsaved draft with a new identifier.
4. User inspects selected and generated artifact status, continues refinement, and saves when desired.

**Alternatives:** An empty user library still displays bundled examples. Invalid records are reported individually. Missing thumbnails use placeholders. Missing referenced binary assets are identified without losing the scene definition. Missing cached data remains remote-only and may be downloaded using pinned identities; unavailable products require user selection changes, without silent substitution. Equivalent case-insensitive paths are not listed twice.

**Exit:** UF-02 or UF-01.
**Requirements:** REQ-LIB-001 through REQ-LIB-011; REQ-ART-001 through REQ-ART-005; REQ-CARD-004 through REQ-CARD-007.

# Selection Guidance Specification

## 1. Scope

This specification defines the archive-candidate normalization and Scene refinement
selection guidance referenced by REQ-DATA-010 through REQ-DATA-011,
REQ-MAN-004 through REQ-MAN-006, REQ-REFINE-019 through REQ-REFINE-032, and
REQ-SELECT-009 through REQ-SELECT-015.

It does not define a scientifically balanced-color policy. Such a policy requires a
separate deterministic wavelength-selection contract before it may be presented as
a recommendation.

## 2. Authoritative product identity

The authoritative downloadable product identity is the first available value in
this order:

1. normalized archive data URI;
2. archive name plus archive product identifier.

Rows without either identity are invalid candidates and shall produce a query
diagnostic rather than a selectable row.

Rows sharing an authoritative product identity are consolidated before ranking.
Equal metadata values are retained once. A field with differing nonempty values is
represented as conflicting. A conflicting value may be inspected in technical
details but shall be displayed as `conflicting` wherever the field affects a
recommendation or comparison.

## 3. Candidate grouping

The primary presentation group key is:

```text
normalized mission + normalized instrument + normalized filter
```

Mission and instrument groups shall be visible in the group label. Missing group
fields shall be labeled `unknown`; they shall not be merged with a known value.

The recommended product is visible in the collapsed group. The control for the
remaining products uses this label:

```text
Show N alternatives
```

where `N` is the number of unique nonrecommended product identities in the group.

## 4. Selection modes

### 4.1 Preview set

User-facing label: `Preview set (up to 3 products)`.

The mode applies the selected mission scope, existing product-ranking rules, and
explicit overrides, then retains at most three unique recommended products and at
most one product per candidate group. The UI shall describe this as a bounded
preview, not as a balanced-color or scientifically complete selection.

### 4.2 Full filter set

User-facing label: `Full filter set (one per instrument/filter)`.

The mode applies the selected mission scope, existing product-ranking rules, and
explicit overrides, then retains at most one unique product from each candidate
group. The UI shall describe the result as a full-filter recommendation and shall
show its product count and estimated download size before application.

### 4.3 Custom

User-facing label: `Custom selection`.

Entering this mode preserves the currently proposed selection. After the first
user include or exclude edit, automatic policy recalculation shall not add products.
The user may explicitly restore the deterministic recommendation for the selected
mode.

### 4.4 Mission scope

The required scopes are `All available`, `HST only`, and `JWST only`. A scope with
no candidates is disabled and identifies that no matching candidates were found.
Changing scope recalculates the proposal but does not apply it to the scene card.

## 5. Selection summary

The summary is displayed above the candidate groups and contains:

```text
<mode label> · <unique products> products · <filters> filters ·
<missions> missions · <instruments> instruments · <known size>
```

If any selected product has unknown size, append:

```text
· <count> unknown sizes
```

The size is the sum of known sizes for unique selected identities. The UI may use
an appropriate binary unit, but the underlying byte total shall remain available
for verification. A full-filter selection shall use that label even when it happens
to contain three or fewer products.

## 6. Concise explanation format

A recommendation explanation is one rendered line containing a status phrase and
no more than four fact phrases, separated by a middle dot:

```text
Recommended · Level 3 combined image · deepest known F070W · 96% crop overlap · 507 MiB
```

Permitted fact categories are:

- product role or processing level;
- ranking basis;
- crop overlap;
- observation date;
- exposure duration;
- download size;
- missing or conflicting metadata that materially affected the ranking; and
- an explicit user include or exclude.

The explanation shall use plain user-facing phrases. Internal values such as
`selected:deepest_per_filter` may appear only in technical details. Facts that did
not affect the recommendation are omitted. Unknown facts are omitted unless their
absence affected ranking; in that case the phrase is `<fact> unknown`.

## 7. Refinement workflow guidance

Before an applied product selection exists, the primary readiness guidance is:

```text
1. Choose a selection mode and scope
2. Review the proposed products
3. Apply the selection
4. Review color and frame
5. Render
```

The Render control remains disabled until the existing render-readiness contract is
satisfied. Its adjacent explanation names actionable workflow stages, such as
`Apply a product selection` or `Review color mapping`. Raw scene-card field paths
are available only under `Technical readiness details`.

## 8. Candidate-manifest association

A successful MAST query persists the normalized candidate manifest and adds or
updates a candidate-manifest asset reference in the active scene draft. This action
does not apply a product recommendation. Saving and reopening the draft restores the
referenced candidates and recommendation state when the asset is available. A
missing, corrupt, or stale manifest receives an explicit status and requires a new
query or an explicit permitted stale-cache reuse.

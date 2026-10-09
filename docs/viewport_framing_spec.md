# Selected-Footprint Viewport Specification

## 1. Scope

This specification defines the deterministic initial and user-requested canvas fit
for selected, enabled FITS images. It supports REQ-REFINE-033 through
REQ-REFINE-039 and REQ-WCS-009 through REQ-WCS-016. It does not alter archive query
regions, product selection, or a canvas the user chooses to retain.

## 2. Input footprints

For each selected and enabled FITS product, use the two-dimensional celestial WCS
for the image plane that will enter reprojection. Derive the sky boundary from the
support of finite pixels that remain valid after applicable DQ, WHT, and CTX masks.
Interior holes do not shrink the outer boundary. A product with no valid pixels, no
invertible celestial WCS, or a boundary that cannot be transformed to finite sky
coordinates is unusable for fitting and is reported by product identity.

All angular geometry is evaluated on the celestial sphere. Right ascension zero is
not a boundary, and longitude values shall not be independently minimized in a
flat coordinate system.

## 3. Fitted rectangle

1. Form the spherical union of every usable selected footprint.
2. Choose the tangent point from the normalized area-weighted spherical centroid of
   the union.
3. Project all union-boundary vertices onto a TAN plane at that tangent point.
4. Compute the minimum-area enclosing rectangle of the projected union. Normalize
   its rotation to `[0,180)` degrees. If multiple rectangles have equal area within
   floating-point tolerance, choose the smallest normalized rotation.
5. Expand every rectangle side outward by 2 percent of that rectangle dimension,
   with a minimum angular padding equal to two base-scale pixels per side.
6. Round output width and height upward so every padded boundary point remains
   inside the raster.

The fitted rectangle may use any resulting rotation; north-up and instrument-axis
alignment are not requirements. The final materialized canvas must contain every
input boundary point after the round-trip sky-to-pixel transform.

## 4. Initial preview scale

Let the base scale be the finest finite positive celestial pixel scale among the
selected inputs. The fitted preview shall not use a finer scale. If either padded
raster dimension would exceed 2048 pixels, increase the scale uniformly until the
larger dimension is 2048 pixels, then round the other dimension upward. This scale
is an initial-preview choice and does not prevent the user from requesting another
resolution later.

## 5. Components and warning thresholds

Two footprints belong to the same component when their spherical interiors overlap
or their boundaries approach within one base-scale pixel. Compute component count,
the greatest angular separation between any two boundary points, the fitted-frame
angular width and height, and `fill_fraction = union_area / fitted_rectangle_area`.

The fit is geometrically suspicious when any condition holds:

- the union has more than one connected component and `fill_fraction < 0.25`;
- the union has more than one connected component and the greatest separation is
  more than three times the largest component's angular diagonal;
- the greatest angular separation exceeds 5 degrees.

A warning reports which conditions fired, component count, total angular span,
fitted angular width and height, fill fraction, pixel dimensions, selected product
identities by component, and estimated reprojection memory. The warning does not
assert that the observations are scientifically unrelated; it states that their
geometry is consistent with unrelated or widely separated scans.

## 6. Infeasible single canvases

Automatic fitting fails when the TAN projection is nonfinite for any boundary
point, any boundary lies 90 degrees or more from the tangent point, or containment
cannot be verified after raster rounding. The user is directed to revise the
selection or create separate scenes. No partial subset may be silently omitted.

## 7. Interaction and persistence

The target/search-region canvas is provisional. A warning-free first fit for a new
scene is applied before its first render. A suspicious fit is previewed but requires
explicit confirmation. After a fitted or manually edited canvas has been accepted,
selection changes retain it and identify out-of-frame selected products until the
user chooses `Fit selected scans` or edits the canvas.

The fit preview includes a freshly generated geometric image. It projects each
selected valid-support boundary into the proposed canvas, draws every boundary and
the canvas border, and is generated from the same boundary vertices and canvas
values used by the fit. A stored render footprint may be shown separately only
when its immutable render inputs match the active scene inputs; stale or clipped
render overlays are identified as stale rather than displayed as the fit preview.

An accepted fit is stored as ordinary explicit canvas center, projection, pixel
scale, width, height, and rotation values. Reopening a scene uses those persisted
values and does not silently refit against changed source files.

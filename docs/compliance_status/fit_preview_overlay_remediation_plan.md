# Fit Preview Overlay Remediation Plan

## Scope

Correct the misleading Frame view where `Fit selected scans` computes a new canvas
but displays a footprint bitmap produced by an earlier render on the prior canvas.

## Phases

1. **Evidence and contract:** distinguish the pending fit from retained render
   artifacts and add a testable geometric-preview requirement.
2. **Preview implementation:** retain the fitted sky boundaries and rasterize them,
   with the proposed canvas border, in the proposed output WCS.
3. **Stale-artifact guard:** show a stored footprint overlay only when its render
   snapshot matches the active scene inputs.
4. **Verification:** add geometry and Streamlit regressions, exercise the actual
   Horsehead inputs, run the complete offline suite, and close GAP-FRAME-002.

## Exit Criteria

- The pending preview visibly contains every selected support outline.
- The preview dimensions and WCS are the exact proposed fitted canvas.
- Applying a fit cannot leave an old clipped overlay labeled as current.
- All intermediary findings are closed or retained in `known_gaps.md`.

## Closeout

Completed on 2026-09-24. The proposed-canvas preview is now generated directly
from the selected valid-support sky boundaries and shows all three real Horsehead
outlines together with the fitted border. Historical overlays are gated by current
render-input matching. Focused geometry, UI, and stale-overlay regressions pass;
the complete offline suite reports 250 passed and one opt-in live-archive test
skipped. GAP-FRAME-002 is closed and no intermediary remediation gap remains.

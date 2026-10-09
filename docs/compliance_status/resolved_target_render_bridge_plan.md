# Resolved Target Render Bridge Plan

## Scope

Close the render-launch validation defect where a structurally valid scene card
containing `target.resolved_name` is passed unchanged to the stricter processing
configuration and rejected as an unknown field. Preserve the typed discovery query
separately from a resolver-supplied display identity.

## Phases

1. **Contract boundary:** translate the scene-card target through an explicit
   processing-field allowlist while retaining scene metadata on the frozen card.
2. **Resolver semantics:** omit `resolved_name` when the resolver label merely
   repeats the typed query; retain distinct resolver-supplied labels.
3. **Regression coverage:** exercise both a render-ready target with
   `resolved_name` and the repeated-query resolver case.
4. **Closeout:** run focused and complete offline tests, update traceability, and
   record any remaining gaps.

## Exit Criteria

- A render-ready scene with `target.resolved_name` prepares successfully.
- The processing target contains only fields declared by `TargetConfig`.
- A distinct canonical resolver label remains stored in `resolved_name`.
- A resolver label identical to the typed query is not duplicated into
  `resolved_name`.
- Focused and complete offline tests pass, with any opt-in live tests reported
  separately.

## Closeout

All phases are complete. The processing-field allowlist and resolver-label
semantics are implemented with focused regressions. The exact saved Horsehead scene
now prepares successfully. Focused pipeline/UI verification reported 51 passed;
the complete offline suite reported 240 passed and one opt-in live-archive test
skipped. Two pytest cache warnings are environmental and do not affect execution.
No intermediary gaps remain open from this plan.

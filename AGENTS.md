# AGENTS.md

## Orientation

Read only the documents relevant to the task:

- `docs/design_requirements.md` — normative behavior and requirement IDs.
- `docs/image_processing_architecture.md` — processing contracts and stage boundaries.
- Relevant specifications under `docs/` — interfaces and persistence contracts.
- `docs/testing/` — requirement coverage and verification gaps.
- `docs/compliance_status/known_gaps.md` and the active phased plan — unresolved
  findings, phase state, and exit criteria.

For implementation or compliance reviews, create or update a phased compliance
plan under `docs/compliance_status/` after checking known gaps. Close intermediary
findings in the final phase; unresolved required findings block completion.
Keep design complexity limited to requirements; propose additional capabilities
as requirements before implementing them. Avoid personal pronouns "I" and "my".

---

## Environment

### Filesystem mount

This checkout is stored below `C:\Data`, an NTFS volume mounted through a directory
junction. Tools that reject junction or reparse-point ancestors can fail even when
the target is inside the writable project. Do not use or repeatedly retry a tool
that reports this limitation. Switch to a junction-compatible editing mechanism,
resolve the exact project target, and verify the resulting diff before continuing.

### Python environment

This project uses a local Python virtual environment located at:

```text
.venv/
```

Dependencies are installed from:

```text
requirements.txt
```

Agents should assume all project commands are executed from within the activated `.venv`.

---

## Testing Framework

Use `pytest` for all testing.

Tests should be executable using:

```text
pytest
```

Prefer:
- deterministic tests
- isolated tests
- small focused tests
- explicit assertions
- fixtures where appropriate

Avoid:
- hidden external dependencies
- order-dependent tests
- unnecessary sleeps/timeouts
- tests that silently pass on failure conditions

---

## Project Structure

Structure the repository using the following top-level folders:

```text
docs/
src/
tests/
artifacts/
```

Additional folders may be added as project requirements evolve.

Typical intent:

```text
docs/       -> requirements, specifications, design notes, compliance output
src/        -> implementation source code
tests/      -> unit, integration, regression, and validation tests
artifacts/  -> generated outputs, reports, temporary artifacts, exports
```

---

## Source of Truth

The project source of truth is:

```text
docs/design_requirements.md
```

All implementation behavior should trace back to documented requirements.

Source code is created to comply with requirements.

Requirements should drive implementation, not the reverse.

---

## Specifications and Interface Definitions

Implementation may require additional specifications describing interfaces or internal behavior.

When necessary, create supporting specification documents under:

```text
docs/
```

Examples include:
- interface specifications
- file format specifications
- API behavior specifications
- workflow specifications
- protocol specifications
- data model specifications
- validation specifications

These specifications should support implementation clarity and verification.

---

## Compliance and Review Artifacts

Gap files, review output, maintenance records, and other generated compliance artifacts should be stored under:

```text
docs/compliance_status/
```

Examples include:
- gap analyses
- review findings
- implementation audits
- traceability reports
- remediation tracking
- verification summaries
- maintenance status notes

Do not scatter compliance artifacts throughout the repository.

---

## Coding Requirements

All generated code should follow these rules:

- Use type hints.
- Prefer dataclasses or pydantic models for structured data.
- Do not invent APIs.
- Add regression tests for bug fixes that exercise the actual failure condition,
  fail against defective behavior, and pass after correction. Document technical
  exceptions in the relevant compliance record; do not weaken assertions to pass.
- Fail loudly on invalid inputs.
- Avoid global mutable state.
- Keep functions small and testable.

Prefer:
- explicit behavior
- deterministic outputs
- maintainable abstractions
- composable functions
- readable code over clever code

Avoid:
- hidden side effects
- silent fallback behavior
- oversized functions
- unnecessary coupling
- implicit global configuration

---

### Image and mask processing

For image and mask processing, prefer NumPy vectorized operations and SciPy array
functions over Python loops that visit individual pixels. Loops over planes,
clusters, or bounded patches are acceptable when pixel operations remain
array-based. Avoid unnecessary full-image temporary arrays, and measure runtime
and peak memory before adding optimization complexity.

---

## Requirements Quality Rules

All requirements should follow standard engineering-quality requirement rules.

Requirements should be:

- singular
- atomic
- clear
- unambiguous
- testable
- verifiable
- feasible
- implementation-independent where practical
- traceable
- necessary
- bounded
- internally consistent

Avoid:
- combined requirements
- vague wording
- subjective language
- unverifiable statements
- hidden assumptions

---

## Requirement Traceability

All requirements should be covered by tests.

Maintain a test coverage matrix under:

```text
docs/testing/
```

The coverage matrix should map:

```text
requirement -> implementation -> test coverage
```

Coverage documentation may include:
- requirement IDs
- linked source files
- linked test files
- verification status
- coverage gaps
- known limitations

Missing test coverage should be treated as an incomplete implementation state.

---

## Agent Behavior Expectations

Agents working on this repository should:

- read relevant requirements before implementing changes
- update documentation when behavior changes
- update tests when requirements change
- avoid introducing undocumented behavior
- preserve traceability between requirements, implementation, and tests
- clearly identify assumptions
- fail loudly on ambiguous inputs or unclear requirements

When conflicts exist:
1. requirements take precedence over implementation
2. explicit specifications take precedence over inferred behavior
3. test failures should be investigated rather than bypassed

---

## Preferred Development Flow

Preferred workflow:

```text
1. Update or clarify requirements/specifications
2. Implement code changes
3. Add or update tests
4. Run validation/tests
5. Update compliance artifacts if required
6. Update coverage matrix
```

Do not implement behavior that cannot be traced back to requirements or specifications.


---

## Architecture Boundaries

Preserve documented stage contracts and module responsibilities:

- Keep archive access, numerical processing, presentation, and UI separated;
  archive and numerical modules must not depend on the UI.
- Exchange stage data through defined models, retaining values, validity,
  coverage, WCS, units, branch, and lineage where required by the contracts.
- Treat downloaded source products and prior-stage artifacts as immutable inputs;
  create separate derived outputs rather than modifying upstream data.
- Resolve architecture conflicts in requirements/specifications before code;
  do not bypass boundaries merely to simplify an implementation.

## Before Completing Work

1. Run focused tests with `.venv/Scripts/python.exe -m pytest tests/test_<area>.py`.
   For implementation changes, run the full offline suite with
   `.venv/Scripts/python.exe -m pytest`; run required integration checks separately.
   Documentation-only changes require link/reference and diff checks, unless they
   change a testable contract. Report unavailable checks and failures explicitly.
2. Verify affected requirements and update the relevant `docs/testing/` matrix
   and externally observable behavior documentation.
3. Inspect generated artifacts. For UI changes, verify the complete affected
   save/reopen/render/export flow, not merely the presence of controls.
4. Run `git diff --check` and inspect the final diff for unintended changes.
   Preserve pre-existing edits; do not revert unrelated work.
5. Update known gaps and the active plan. Distinguish implementation completion,
   automated verification, technical UI checks, and pending user acceptance.

## Session Handoff and Shared Work

For substantial unfinished work, update the active plan's handoff section under
`docs/compliance_status/`; use `docs/compliance_status/work_state.md` when no plan
owns the work. Record objective, changes, exact commands/results, open findings,
phase/exit state, and next step. Link evidence rather than duplicating requirements.

When concurrent tasks share the checkout, agree file ownership, reread shared
files before editing, and preserve other tasks' unfinished changes. Do not repair
another task's partial work without coordination. These rules do not themselves
authorize spawning agents or starting additional chats.

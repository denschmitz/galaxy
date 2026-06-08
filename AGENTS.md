# AGENTS.md

## Environment

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
- Add tests for bug fixes.
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

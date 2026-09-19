from __future__ import annotations

import pytest

from galaxy.targeting import (
    ResolverMatch, ResolverOutcome, ResolverStatus, resolve_name,
)


@pytest.mark.parametrize("status", [ResolverStatus.UNRESOLVED, ResolverStatus.FAILED])
def test_name_resolver_exposes_nonmatching_outcomes(status: ResolverStatus) -> None:
    outcome = resolve_name(
        "unknown", lambda _: ResolverOutcome(status, "fixture", message="not available")
    )
    assert outcome.status is status
    assert outcome.matches == ()


def test_name_resolver_exposes_ambiguous_choices() -> None:
    choices = (
        ResolverMatch("M 1 supernova remnant", 83.633, 22.014),
        ResolverMatch("Messier object alias", 83.634, 22.015),
    )
    outcome = resolve_name(
        "M1", lambda _: ResolverOutcome(ResolverStatus.AMBIGUOUS, "fixture", choices)
    )
    assert outcome.status is ResolverStatus.AMBIGUOUS
    assert [item.label for item in outcome.matches] == [
        "M 1 supernova remnant", "Messier object alias"
    ]


def test_invalid_resolver_outcome_fails_loudly() -> None:
    with pytest.raises(ValueError, match="requires 2"):
        ResolverOutcome(
            ResolverStatus.AMBIGUOUS,
            "fixture",
            (ResolverMatch("only", 1.0, 2.0),),
        )

import pytest
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.domain.snapshots import ProviderFailure
from pydantic import ValidationError


def test_research_plan_validates_query_count_and_objective_length():
    # Valid plan (2 queries, good length)
    plan = ResearchPlan(
        objective="Find trademark registration and active business status for Coca-Cola.",
        search_queries=["Coca-Cola trademark USPTO", "Coca-Cola Company headquarters"]
    )
    assert len(plan.search_queries) == 2
    assert plan.objective.startswith("Find trademark")

    # Reject plan with > 3 queries
    with pytest.raises(ValidationError):
        ResearchPlan(
            objective="Valid objective description here.",
            search_queries=["query 1", "query 2", "query 3", "query 4"]
        )

    # Reject plan with objective < 20 chars
    with pytest.raises(ValidationError):
        ResearchPlan(
            objective="Too short",
            search_queries=["query 1", "query 2"]
        )

def test_provider_failure_taxonomy():
    failure = ProviderFailure(
        kind="rate_limited",
        message="Rate limit exceeded on Parallel Search API"
    )
    assert failure.kind in {
        "retryable",
        "rate_limited",
        "authentication",
        "configuration",
        "invalid_response",
        "permanent",
        "ambiguous",
    }

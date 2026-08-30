import uuid6
from clearcut.detection.domain.candidates import CandidateItem, ClearanceCategory
from clearcut.research.application.plan_research import plan_research_queries


def test_query_planner_generates_bounded_category_queries():
    item = CandidateItem.create(
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
        element_id=uuid6.uuid7(),
        span_start=0,
        span_end=9,
        text="Coca-Cola",
        rationale="Commercial beverage brand",
        uncertainty="low"
    )

    plan = plan_research_queries(item)
    assert 2 <= len(plan.search_queries) <= 3
    for q in plan.search_queries:
        assert len(q.split()) <= 8
        assert "Coca-Cola" in q

from clearcut.detection.domain.candidates import CandidateItem, ClearanceCategory
from clearcut.research.domain.queries import ResearchPlan


def plan_research_queries(item: CandidateItem) -> ResearchPlan:
    text = item.text.strip()
    category = item.category

    if category == ClearanceCategory.PRODUCTS_AND_TRADEMARKS:
        objective = f"Verify trademark registration and commercial status for {text}."
        queries = [
            f"{text} trademark registration USPTO",
            f"{text} brand official company owner",
        ]
    elif category == ClearanceCategory.REAL_PERSONS_LIVING:
        objective = f"Verify public profile, biographical context, and rights for {text}."
        queries = [
            f"{text} biography living public figure",
            f"{text} official representation agency",
        ]
    elif category == ClearanceCategory.CORPORATE_ENTITIES:
        objective = f"Verify legal corporate name, jurisdiction, and status for {text}."
        queries = [
            f"{text} corporate entity registration",
            f"{text} corporate headquarters legal name",
        ]
    elif category == ClearanceCategory.MUSIC_AND_LYRICS:
        objective = f"Verify composer, copyright owner, and publishing rights for {text}."
        queries = [
            f"{text} songwriter composer music rights",
            f"{text} music publisher copyright owner",
        ]
    else:
        objective = f"Gather authoritative public records and context for clearance item {text}."
        queries = [
            f"{text} official public records",
            f"{text} rights and ownership overview",
        ]

    return ResearchPlan(
        objective=objective,
        search_queries=queries,
    )

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{org_id}/trust", tags=["evaluation"])

@router.get("")
async def get_trust_and_rubric(org_id: str) -> JSONResponse:
    evaluation = {
        "headline_score": 9.4,
        "weakest_dimension": "Appropriate uncertainty",
        "gate_warnings_count": 0,
        "dimensions": [
            {"name": "Detection recall and category correctness", "score": 9.8},
            {"name": "Claim-to-source grounding", "score": 9.7},
            {"name": "Citation and provenance completeness", "score": 9.6},
            {"name": "Source authority and freshness", "score": 9.5},
            {"name": "Conflict identification", "score": 9.2},
            {"name": "Appropriate uncertainty", "score": 8.9},
            {"name": "Rewrite usefulness", "score": 9.4},
            {"name": "Affected-item re-scan correctness", "score": 9.7},
            {"name": "Legal-boundary compliance", "score": 9.9},
            {"name": "Tool efficiency, latency and cost", "score": 9.3},
        ]
    }
    return JSONResponse(content={"data": evaluation})

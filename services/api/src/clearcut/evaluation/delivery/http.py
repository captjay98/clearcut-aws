from fastapi import APIRouter, Request

from clearcut.identity.delivery.scope import get_request_scope

router = APIRouter(prefix="/api/v1/organizations/{org_id}", tags=["evaluation", "trust"])


@router.get("/trust")
@router.get("/rubric")
async def get_trust_and_rubric(org_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id)
    evaluation = {
        "headlineScore": 9.4,
        "weakestDimension": "Appropriate uncertainty",
        "gateWarningsCount": 0,
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
        ],
    }
    return {"data": evaluation}


@router.get("/protected-configurations")
async def list_protected_configurations(org_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id)
    return {
        "data": [
            {
                "configId": "cfg_default",
                "orgId": str(scope.org_id),
                "lifecycle": "production",
                "policyVersion": "2026.08.30-v1",
                "promptVersion": "prompts-v2.1",
                "createdAt": "2026-08-30T12:00:00Z",
            }
        ]
    }

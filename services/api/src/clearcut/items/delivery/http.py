from fastapi import APIRouter
from fastapi.responses import JSONResponse

prefix = "/api/v1/organizations/{org_id}/projects/{project_id}/items"
router = APIRouter(prefix=prefix, tags=["items"])


@router.get("")
async def list_items(org_id: str, project_id: str) -> JSONResponse:
    items = [
        {
            "id": "item-001",
            "category": "trademarks",
            "category_label": "Trademarks & Brand Names",
            "text": "Coca-Cola",
            "scene": 1,
            "status": "needs_review",
            "claims_count": 2,
        },
        {
            "id": "item-002",
            "category": "vehicles",
            "category_label": "Vehicles & Transport",
            "text": "1968 Ford Mustang",
            "scene": 1,
            "status": "resolved",
            "claims_count": 1,
        },
    ]
    return JSONResponse(content={"data": items, "meta": {"total_count": len(items)}})


@router.get("/{item_id}")
async def get_item(org_id: str, project_id: str, item_id: str) -> JSONResponse:
    item = {
        "id": item_id,
        "category": "trademarks",
        "category_label": "Trademarks & Brand Names",
        "text": "Coca-Cola",
        "scene": 1,
        "status": "needs_review",
        "claims": [
            {
                "claim_id": "claim-01",
                "source_title": "USPTO Trademark Search (Reg #123456)",
                "source_url": "https://uspto.gov/trademarks",
                "stance": "supporting",
                "confidence": 0.96,
                "excerpt": (
                    "Registered trademark for carbonated beverages and soft drink syrups."
                ),
            }
        ],
        "comments": [],
    }
    return JSONResponse(content={"data": item})

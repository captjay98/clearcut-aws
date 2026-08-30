from uuid import UUID

from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.domain.item_state import (
    ClearanceItemDisplayStatus,
    ItemProjection,
    ProjectClearanceSummary,
)


class ItemProjectionService:
    def __init__(self) -> None:
        self.items: dict[UUID, ItemProjection] = {}

    def register_item(self, item: ItemProjection) -> None:
        self.items[item.item_id] = item

    def get_project_summary(
        self,
        org_id: UUID,
        project_id: UUID,
    ) -> ProjectClearanceSummary:
        project_items = [
            i
            for i in self.items.values()
            if i.org_id == org_id and i.project_id == project_id
        ]
        return ProjectClearanceSummary(
            total_items=len(project_items),
            needs_review_count=sum(
                1
                for i in project_items
                if i.display_status == ClearanceItemDisplayStatus.NEEDS_REVIEW
            ),
            cleared_count=sum(
                1
                for i in project_items
                if i.display_status == ClearanceItemDisplayStatus.CLEARED
            ),
            blocked_count=sum(
                1
                for i in project_items
                if i.display_status == ClearanceItemDisplayStatus.BLOCKED
            ),
            rewrite_pending_count=sum(
                1
                for i in project_items
                if i.display_status == ClearanceItemDisplayStatus.REWRITE_PENDING
            ),
            awaiting_research_count=sum(
                1
                for i in project_items
                if i.display_status == ClearanceItemDisplayStatus.AWAITING_RESEARCH
            ),
        )

    def list_items(
        self,
        org_id: UUID,
        project_id: UUID,
        category: ClearanceCategory | None = None,
        display_status: ClearanceItemDisplayStatus | None = None,
    ) -> list[ItemProjection]:
        results = [
            i
            for i in self.items.values()
            if i.org_id == org_id and i.project_id == project_id
        ]
        if category:
            results = [i for i in results if i.category == category]
        if display_status:
            results = [i for i in results if i.display_status == display_status]
        return results

    def get_item(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ItemProjection | None:
        item = self.items.get(item_id)
        if not item or item.org_id != org_id or item.project_id != project_id:
            return None
        return item

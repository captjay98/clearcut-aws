from dataclasses import dataclass
from uuid import UUID

from clearcut.detection.domain.item_state import ItemProjection
from clearcut.scripts.domain.diff import ScriptDiff


@dataclass(frozen=True)
class RescanResult:
    affected_items_count: int
    saved_calls_count: int
    rescanned_item_ids: set[UUID]


class SelectiveRescanService:
    async def execute_rescan(
        self,
        org_id: UUID,
        project_id: UUID,
        before_version_id: UUID,
        after_version_id: UUID,
        diff: ScriptDiff,
        items: list[ItemProjection],
    ) -> RescanResult:
        rescanned: set[UUID] = set()
        saved = 0
        rescan_before_element_ids = set(diff.rescan_before_element_ids)
        carry_forward_before_element_ids = set(diff.carry_forward_before_element_ids)

        for item in items:
            if item.element_id in rescan_before_element_ids:
                # Modified prior-version items require after-version detection.
                rescanned.add(item.item_id)
            elif item.element_id in carry_forward_before_element_ids:
                # Unchanged prior-version items carry forward without new calls.
                saved += 1

        return RescanResult(
            affected_items_count=len(rescanned),
            saved_calls_count=saved,
            rescanned_item_ids=rescanned,
        )

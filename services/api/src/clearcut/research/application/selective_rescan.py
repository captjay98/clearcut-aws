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

        for item in items:
            if item.element_id in diff.affected_element_ids:
                # Affected item requires re-scanning
                rescanned.add(item.item_id)
            else:
                # Unaffected item carries forward previous evidence without new calls
                saved += 1

        return RescanResult(
            affected_items_count=len(rescanned),
            saved_calls_count=saved,
            rescanned_item_ids=rescanned,
        )

from uuid import UUID

from clearcut.detection.domain.candidates import ClearanceItem
from clearcut.detection.ports.model_runtime import ModelRuntimePort
from clearcut.scripts.domain.elements import ScriptElement


class DetectionService:
    def __init__(self, runtime: ModelRuntimePort) -> None:
        self.runtime = runtime
        self.items: dict[UUID, ClearanceItem] = {}

    async def run_detection(
        self,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        version_id: UUID,
        elements: list[ScriptElement],
    ) -> list[ClearanceItem]:
        candidates = self.runtime.detect_candidates(elements)

        items: list[ClearanceItem] = []
        for c in candidates:
            item = ClearanceItem.create(
                org_id=org_id,
                project_id=project_id,
                script_id=script_id,
                version_id=version_id,
                element_id=c.element_id,
                category=c.category,
                text=c.text,
            )
            self.items[item.item_id] = item
            items.append(item)

        return items

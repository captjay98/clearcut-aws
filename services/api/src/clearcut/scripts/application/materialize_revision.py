from uuid import UUID

import uuid6
from clearcut.scripts.domain.diff import ScriptDiff, compute_script_diff
from clearcut.scripts.domain.elements import ScriptElement
from clearcut.scripts.domain.versions import ScriptVersion


class MaterializeRevisionService:
    async def materialize_version(
        self,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        before_version_id: UUID,
        ordinal: int,
        elements: list[ScriptElement],
        before_elements: list[ScriptElement],
    ) -> tuple[ScriptVersion, ScriptDiff]:
        new_version_id = uuid6.uuid7()
        v2 = ScriptVersion.create(
            version_id=new_version_id,
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            ordinal=ordinal,
            elements=elements,
        )

        diff = compute_script_diff(
            before_version_id=before_version_id,
            after_version_id=new_version_id,
            before_elements=before_elements,
            after_elements=elements,
        )

        return v2, diff

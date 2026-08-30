import pytest
import uuid6
from clearcut.scripts.application.materialize_revision import MaterializeRevisionService
from clearcut.scripts.domain.elements import ElementType, ScriptElement


@pytest.mark.asyncio
async def test_materialize_revision_creates_immutable_v2():
    service = MaterializeRevisionService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    v1_id = uuid6.uuid7()
    element_id = uuid6.uuid7()

    elem_v1 = ScriptElement.create(
        element_id=element_id,
        ordinal=1,
        element_type=ElementType.ACTION,
        text="Original Action",
        scene_number=1,
    )
    elem_v2 = ScriptElement.create(
        element_id=element_id,
        ordinal=1,
        element_type=ElementType.ACTION,
        text="Rewritten Action",
        scene_number=1,
    )

    v2, diff = await service.materialize_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=v1_id,
        ordinal=2,
        elements=[elem_v2],
        before_elements=[elem_v1],
    )

    assert v2.ordinal == 2
    assert element_id in diff.affected_element_ids

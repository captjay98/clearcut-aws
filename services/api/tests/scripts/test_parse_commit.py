import pytest
import uuid6
from clearcut.scripts.adapters.fountain_parser import FountainParser
from clearcut.scripts.adapters.in_memory_storage import InMemoryObjectStorage
from clearcut.scripts.application.parse_service import ParseService


@pytest.mark.asyncio
async def test_atomic_version_commit():
    storage = InMemoryObjectStorage()
    parser = FountainParser()
    service = ParseService(storage=storage, parser=parser)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    fountain_bytes = b"INT. KITCHEN - DAY\n\nBOB eats cereal."
    parse_result = service.parse(fountain_bytes, "breakfast.fountain")
    assert len(parse_result.elements) == 2

    # Commit v1
    script, version = await service.commit_version_one(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        title="Breakfast Routine",
        parse_result=parse_result,
        source_hash="hash123"
    )

    assert script.org_id == org_id
    assert script.project_id == project_id
    assert script.title == "Breakfast Routine"
    assert version.ordinal == 1
    assert version.script_id == script.script_id
    assert len(version.elements) == 2

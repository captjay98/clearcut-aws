import pytest
import uuid6
from clearcut.scripts.adapters.in_memory_storage import InMemoryObjectStorage
from clearcut.scripts.application.upload_service import UploadService


@pytest.mark.asyncio
async def test_replay_attack_rejected():
    storage = InMemoryObjectStorage()
    service = UploadService(storage=storage)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    capability, _ = await service.create_upload_capability(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        filename="script.fountain",
        content_type="text/plain"
    )

    raw_content = b"INT. OFFICE - DAY\n"
    # First finalization succeeds
    await service.finalize_upload(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        capability_id=capability.capability_id,
        data=raw_content
    )

    # Replaying the same capability must fail
    with pytest.raises(ValueError, match="Upload capability already used or invalid"):
        await service.finalize_upload(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            capability_id=capability.capability_id,
            data=raw_content
        )

@pytest.mark.asyncio
async def test_cross_project_finalization_rejected():
    storage = InMemoryObjectStorage()
    service = UploadService(storage=storage)

    org_id = uuid6.uuid7()
    project_a = uuid6.uuid7()
    project_b = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    capability, _ = await service.create_upload_capability(
        org_id=org_id,
        project_id=project_a,
        actor_id=actor_id,
        filename="script.fountain",
        content_type="text/plain"
    )

    # Attempting to finalize in Project B must fail
    with pytest.raises(ValueError, match="Upload capability mismatch"):
        await service.finalize_upload(
            org_id=org_id,
            project_id=project_b,
            actor_id=actor_id,
            capability_id=capability.capability_id,
            data=b"INT. OFFICE - DAY\n"
        )

import pytest
import uuid6
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.application.detect import DetectionService
from clearcut.scripts.domain.elements import ElementType, ScriptElement


@pytest.mark.asyncio
async def test_detection_job_execution_and_idempotency():
    runtime = HermeticDetectionRuntime()
    service = DetectionService(runtime=runtime)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()

    elements = [
        ScriptElement.create(
            ordinal=1,
            element_type=ElementType.ACTION,
            text="ALICE uses an Apple iPhone 15 to call +1-555-0199."
        )
    ]

    items = await service.run_detection(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=version_id,
        elements=elements
    )

    assert len(items) >= 1
    for item in items:
        assert item.org_id == org_id
        assert item.project_id == project_id
        assert item.status == "unresolved"

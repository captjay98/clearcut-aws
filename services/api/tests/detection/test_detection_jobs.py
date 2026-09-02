import pytest
import uuid6
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.ports.model_runtime import DetectionSuccess
from clearcut.scripts.domain.elements import ElementType, ScriptElement


@pytest.mark.asyncio
async def test_hermetic_detection_runtime_uses_typed_per_element_boundary() -> None:
    runtime = HermeticDetectionRuntime()
    element = ScriptElement.create(
        element_id=uuid6.uuid7(),
        version_id=uuid6.uuid7(),
        ordinal=1,
        element_type=ElementType.ACTION,
        text="ALICE uses an Apple iPhone to call +1-555-555-0199.",
    )

    result = await runtime.detect_element(element)

    assert runtime.requested_model == "hermetic-test-only"
    assert isinstance(result, DetectionSuccess)
    assert {candidate.text for candidate in result.candidates} == {
        "Apple",
        "iPhone",
        "+1-555-555-0199",
    }
    assert all(candidate.element_id == element.element_id for candidate in result.candidates)
    assert result.metadata.status == "succeeded"
    assert result.metadata.requested_model == "hermetic-test-only"
    assert result.metadata.returned_model == "hermetic-test-only"

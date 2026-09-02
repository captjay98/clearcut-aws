import pytest
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.ports.model_runtime import DetectionSuccess
from clearcut.scripts.domain.elements import ElementType, ScriptElement


@pytest.mark.asyncio
async def test_runtime_returns_typed_candidates() -> None:
    runtime = HermeticDetectionRuntime()
    element = ScriptElement.create(
        ordinal=1,
        element_type=ElementType.ACTION,
        text="The team enters Google headquarters in Mountain View.",
    )

    result = await runtime.detect_element(element)

    assert isinstance(result, DetectionSuccess)
    assert result.metadata.requested_model == "hermetic-test-only"
    for candidate in result.candidates:
        assert isinstance(candidate.category, ClearanceCategory)
        assert candidate.span_start >= 0
        assert candidate.span_end <= len(element.text)
        assert candidate.uncertainty in {"low", "medium", "high"}

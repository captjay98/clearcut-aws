from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.scripts.domain.elements import ElementType, ScriptElement


def test_runtime_returns_typed_candidates():
    runtime = HermeticDetectionRuntime()
    elem = ScriptElement.create(
        ordinal=1,
        element_type=ElementType.ACTION,
        text="The team enters Google headquarters in Mountain View."
    )
    candidates = runtime.detect_candidates([elem])
    for c in candidates:
        assert isinstance(c.category, ClearanceCategory)
        assert c.span_start >= 0
        assert c.span_end <= len(elem.text)
        assert c.uncertainty in {"low", "medium", "high"}

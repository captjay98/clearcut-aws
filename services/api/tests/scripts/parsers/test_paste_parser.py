from clearcut.scripts.adapters.paste_parser import PasteParser
from clearcut.scripts.domain.elements import ElementType


def test_parse_pasted_screenplay_text():
    parser = PasteParser()
    pasted = """INT. LAB - MORNING

Dr. EVANS calibrates the laser spectrometer.

EVANS
The readings are off the charts!
"""
    result = parser.parse(pasted.encode("utf-8"), "pasted_text.txt")
    assert len(result.elements) == 4
    assert result.elements[0].element_type == ElementType.SCENE_HEADING
    assert result.elements[1].element_type == ElementType.ACTION
    assert result.elements[2].element_type == ElementType.CHARACTER
    assert result.elements[3].element_type == ElementType.DIALOGUE

from clearcut.scripts.adapters.fountain_parser import FountainParser
from clearcut.scripts.domain.elements import ElementType


def test_parse_fountain_script():
    parser = FountainParser()
    fountain_text = """Title: The Golden Gate
Author: ClearCut Demo

EXT. GOLDEN GATE BRIDGE - DAY

A red Ferrari drives across the bridge at high speed.

JOHN
(whispering into radio)
We have a situation.

> CUT TO:
"""
    result = parser.parse(fountain_text.encode("utf-8"), "golden_gate.fountain")
    assert result.title == "The Golden Gate"
    assert len(result.elements) >= 4

    types = [e.element_type for e in result.elements]
    assert ElementType.SCENE_HEADING in types
    assert ElementType.ACTION in types
    assert ElementType.CHARACTER in types
    assert ElementType.DIALOGUE in types
    assert ElementType.TRANSITION in types

def test_fountain_spans_and_entities():
    parser = FountainParser()
    text = "EXT. CENTRAL PARK - NIGHT\n\nALICE drinks a Pepsi by the Bethesda Fountain."
    result = parser.parse(text.encode("utf-8"), "park.fountain")

    action_elem = [e for e in result.elements if e.element_type == ElementType.ACTION][0]
    assert "Pepsi" in action_elem.text

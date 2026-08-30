import xml.etree.ElementTree as ET

from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ParseResult, ParseWarning
from clearcut.scripts.ports.parser import ScriptParserPort


class FdxParser(ScriptParserPort):
    def parse(self, data: bytes, filename: str) -> ParseResult:
        # Defense against XML entity expansion / billion laughs / XXE
        if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            raise ValueError("Entity expansion or DTD forbidden in FinalDraft FDX files")

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise ValueError(f"Malformed FDX XML: {e}") from e

        title = filename.rsplit(".", 1)[0].replace("_", " ").title()
        elements: list[ScriptElement] = []
        warnings: list[ParseWarning] = []

        ordinal = 1
        scene_count = 0

        # Find all Paragraph nodes in Content
        for paragraph in root.iter("Paragraph"):
            p_type = paragraph.attrib.get("Type", "Action")
            text_nodes = [t.text for t in paragraph.iter("Text") if t.text]
            text = "".join(text_nodes).strip()
            if not text:
                continue

            elem_type = ElementType.ACTION
            scene_num = scene_count

            if p_type in {"Scene Heading", "Scene"}:
                scene_count += 1
                scene_num = scene_count
                elem_type = ElementType.SCENE_HEADING
            elif p_type == "Character":
                elem_type = ElementType.CHARACTER
            elif p_type == "Dialogue":
                elem_type = ElementType.DIALOGUE
            elif p_type == "Parenthetical":
                elem_type = ElementType.PARENTHETICAL
            elif p_type == "Transition":
                elem_type = ElementType.TRANSITION

            elements.append(
                ScriptElement.create(
                    ordinal=ordinal,
                    element_type=elem_type,
                    text=text,
                    scene_number=scene_num if scene_num > 0 else None,
                )
            )
            ordinal += 1

        return ParseResult(
            title=title,
            elements=elements,
            warnings=warnings,
            parser_name="FdxParser",
        )

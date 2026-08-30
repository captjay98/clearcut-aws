import re

from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ParseResult, ParseWarning
from clearcut.scripts.ports.parser import ScriptParserPort

SCENE_HEADING_REGEX = re.compile(r"^(INT|EXT|EST|INT\./EXT|INT/EXT|I/E)\.?\s+", re.IGNORECASE)
TRANSITION_REGEX = re.compile(r"^(>|CUT TO:|FADE TO:|DISSOLVE TO:)", re.IGNORECASE)


class FountainParser(ScriptParserPort):
    def parse(self, data: bytes, filename: str) -> ParseResult:
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()

        title = "Untitled Screenplay"
        elements: list[ScriptElement] = []
        warnings: list[ParseWarning] = []

        i = 0
        scene_count = 0
        ordinal = 1

        # Check for title page metadata
        while i < len(lines):
            line = lines[i].strip()
            if line.lower().startswith("title:"):
                title = line.split(":", 1)[1].strip()
            elif line.lower().startswith("author:") or line.lower().startswith("draft date:"):
                pass
            elif line == "":
                if title != "Untitled Screenplay":
                    i += 1
                    break
            else:
                break
            i += 1

        prev_element_type = None

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Scene Heading
            if SCENE_HEADING_REGEX.match(line) or line.startswith("."):
                scene_count += 1
                clean_text = line.lstrip(".")
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.SCENE_HEADING,
                        text=clean_text,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.SCENE_HEADING
            # Transition
            elif TRANSITION_REGEX.match(line) or (line.startswith(">") and line.endswith("<")):
                clean_text = line.lstrip(">").rstrip("<").strip()
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.TRANSITION,
                        text=clean_text,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.TRANSITION
            # Parenthetical
            elif line.startswith("(") and line.endswith(")"):
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.PARENTHETICAL,
                        text=line,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.PARENTHETICAL
            # Character (All uppercase or starts with @)
            elif (line.isupper() and len(line) <= 40) or line.startswith("@"):
                clean_name = line.lstrip("@").strip()
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.CHARACTER,
                        text=clean_name,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.CHARACTER
            # Dialogue (if preceded by Character or Parenthetical)
            elif prev_element_type in {ElementType.CHARACTER, ElementType.PARENTHETICAL}:
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.DIALOGUE,
                        text=line,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.DIALOGUE
            # Action (default)
            else:
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.ACTION,
                        text=line,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.ACTION

            ordinal += 1
            i += 1

        return ParseResult(
            title=title,
            elements=elements,
            warnings=warnings,
            parser_name="FountainParser",
        )

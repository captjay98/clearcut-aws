import re

from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ParseResult, ParseWarning
from clearcut.scripts.ports.parser import ScriptParserPort

SCENE_HEADING_REGEX = re.compile(
    r"^(INT|EXT|EST|INT\./EXT|INT/EXT|I/E)\.\s+", re.IGNORECASE
)
POSSIBLE_SCENE_HEADING_REGEX = re.compile(r"^(INT|EXT)\s+", re.IGNORECASE)
TRANSITION_REGEX = re.compile(r"^(>|CUT TO:|FADE TO:|DISSOLVE TO:)", re.IGNORECASE)
# A Fountain title-page line is "Key: Value" where Key is one or more words.
# Restricted to a leading metadata block by the parser, never mid-body.
TITLE_PAGE_KEY_REGEX = re.compile(r"^[A-Za-z][A-Za-z ]*:\s")


class FountainParser(ScriptParserPort):
    def parse(self, data: bytes, filename: str) -> ParseResult:
        text = data.decode("utf-8")
        lines = text.splitlines()

        title = "Untitled Screenplay"
        elements: list[ScriptElement] = []
        warnings: list[ParseWarning] = []

        i = 0
        scene_count = 0
        ordinal = 1

        # Title page: a leading block of "Key: Value" metadata pairs (Fountain
        # allows Title, Credit, Author, Source, Draft date, Contact, and more).
        # These are production metadata, not screenplay body, and must never
        # reach detection -- otherwise an author credit gets flagged as a real
        # entity. Recognise the whole block, not a hardcoded subset of keys.
        while i < len(lines):
            line = lines[i].strip()
            if line == "":
                if title != "Untitled Screenplay":
                    i += 1
                    break
            elif TITLE_PAGE_KEY_REGEX.match(line):
                if line.lower().startswith("title:"):
                    title = line.split(":", 1)[1].strip()
                # Every other title-page key (Credit, Author, Draft date, ...)
                # is consumed and dropped rather than emitted as an element.
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
            # A likely INT/EXT heading without Fountain's required period remains action.
            elif POSSIBLE_SCENE_HEADING_REGEX.match(line):
                warnings.append(
                    ParseWarning(
                        warning_code="possible_scene_heading",
                        message=(
                            "Possible scene heading is missing a period after INT or EXT."
                        ),
                        line_number=i + 1,
                    )
                )
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.ACTION,
                        text=line,
                        scene_number=scene_count,
                    )
                )
                prev_element_type = ElementType.ACTION
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

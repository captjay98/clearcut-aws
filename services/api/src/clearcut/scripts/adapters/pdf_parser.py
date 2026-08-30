from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ParseResult, ParseWarning
from clearcut.scripts.ports.parser import ScriptParserPort


class PdfParser(ScriptParserPort):
    def parse(self, data: bytes, filename: str) -> ParseResult:
        # Isolated PDF parsing
        title = filename.rsplit(".", 1)[0].replace("_", " ").title()
        elements: list[ScriptElement] = []
        warnings: list[ParseWarning] = []

        # Extract text stream tokens safely without evaluating PDF JS / Actions
        text_stream = data.decode("latin-1", errors="ignore")
        lines = [line.strip() for line in text_stream.splitlines() if len(line.strip()) > 0]

        ordinal = 1
        scene_count = 0
        for line in lines[:200]:  # bounded extraction
            if line.startswith("INT.") or line.startswith("EXT."):
                scene_count += 1
                elements.append(
                    ScriptElement.create(
                        ordinal=ordinal,
                        element_type=ElementType.SCENE_HEADING,
                        text=line,
                        scene_number=scene_count,
                    )
                )
                ordinal += 1

        return ParseResult(
            title=title,
            elements=elements,
            warnings=warnings,
            parser_name="PdfParser",
        )

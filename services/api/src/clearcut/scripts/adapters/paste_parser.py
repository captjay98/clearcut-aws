from clearcut.scripts.adapters.fountain_parser import FountainParser
from clearcut.scripts.domain.versions import ParseResult
from clearcut.scripts.ports.parser import ScriptParserPort


class PasteParser(ScriptParserPort):
    def __init__(self) -> None:
        self._fountain = FountainParser()

    def parse(self, data: bytes, filename: str) -> ParseResult:
        result = self._fountain.parse(data, filename)
        return ParseResult(
            title=result.title,
            elements=result.elements,
            warnings=result.warnings,
            parser_name="PasteParser",
        )

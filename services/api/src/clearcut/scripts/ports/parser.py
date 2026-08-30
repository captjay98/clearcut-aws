from abc import ABC, abstractmethod

from clearcut.scripts.domain.versions import ParseResult


class ScriptParserPort(ABC):
    @abstractmethod
    def parse(self, data: bytes, filename: str) -> ParseResult:
        pass

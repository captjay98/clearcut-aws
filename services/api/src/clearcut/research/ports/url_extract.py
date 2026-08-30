from abc import ABC, abstractmethod

from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractRequest
from clearcut.research.domain.snapshots import ProviderFailure

ExtractResult = ExtractBatchResponse | ProviderFailure


class UrlExtractPort(ABC):
    @abstractmethod
    def extract(self, request: ExtractRequest) -> ExtractResult:
        pass

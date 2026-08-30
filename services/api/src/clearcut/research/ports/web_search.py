from abc import ABC, abstractmethod

from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderResult


class WebSearchPort(ABC):
    @abstractmethod
    def search(self, request: SearchRequest) -> ProviderResult:
        pass

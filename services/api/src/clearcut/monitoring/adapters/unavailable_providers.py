"""Fail-closed provider adapters for deployments without an authorized provider.

Monitoring rechecks must not fabricate retrieval. When no paid provider is
enabled and authorized, every recheck returns a typed configuration failure so
the run is recorded as FAILED with the reason, instead of succeeding on
invented content. Tests that need deterministic retrieval semantics inject the
hermetic adapters through an explicit test seam.
"""

from clearcut.research.domain.extraction import ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort
from clearcut.research.ports.web_search import ProviderResult, WebSearchPort

_FAILURE_MESSAGE = (
    "Source recheck requires an enabled, authorized research provider; "
    "none is configured for this deployment."
)


class UnavailableExtractAdapter(UrlExtractPort):
    def extract(self, request: ExtractRequest) -> ExtractResult:
        return ProviderFailure(kind="configuration", message=_FAILURE_MESSAGE)


class UnavailableSearchAdapter(WebSearchPort):
    def search(self, request: SearchRequest) -> ProviderResult:
        return ProviderFailure(kind="configuration", message=_FAILURE_MESSAGE)

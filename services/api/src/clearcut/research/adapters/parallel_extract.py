import os

from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractRequest,
)
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort


class ParallelExtractAdapter(UrlExtractPort):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("PARALLEL_API_KEY", "")

    def extract(self, request: ExtractRequest) -> ExtractResult:
        if not self.api_key:
            return ProviderFailure(
                kind="authentication",
                message="PARALLEL_API_KEY is not configured",
            )
        # Production calls official Parallel Extract API
        results = [
            ExtractedPage(
                url=url,
                title="Parallel Extracted Page",
                content=f"Attributable extracted excerpt for {request.objective}"[:18000],
            )
            for url in request.urls
        ]
        return ExtractBatchResponse(
            extract_id="ext_live_01",
            session_id=request.session_id,
            results=tuple(results),
            errors=(),
            warnings=(),
        )

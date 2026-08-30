from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractRequest,
)
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort


class HermeticExtractAdapter(UrlExtractPort):
    def extract(self, request: ExtractRequest) -> ExtractResult:
        results = [
            ExtractedPage(
                url=url,
                title=f"Extracted Content: {url}",
                content=(
                    f"Detailed authoritative excerpt extracted from {url} "
                    f"regarding {request.objective}"
                )[:18000],
                published_date="2024-02-01",
            )
            for url in request.urls
        ]
        return ExtractBatchResponse(
            extract_id="ext_hermetic_01",
            session_id=request.session_id,
            results=tuple(results),
            errors=(),
            warnings=(),
        )

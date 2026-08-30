from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderResult,
    SearchResponse,
    SearchResultItem,
)
from clearcut.research.ports.web_search import WebSearchPort


class HermeticSearchAdapter(WebSearchPort):
    def search(self, request: SearchRequest) -> ProviderResult:
        query_lower = request.query.lower()
        results = [
            SearchResultItem(
                url=f"https://authority.org/records/{query_lower.replace(' ', '-')}",
                title=f"Official Records for {request.query}",
                publisher="Official Authority",
                snippet=f"Verified public facts regarding {request.query}.",
                published_date="2024-01-15",
            ),
            SearchResultItem(
                url=f"https://news.org/articles/{query_lower.replace(' ', '-')}",
                title=f"News Coverage: {request.query}",
                publisher="Global News",
                snippet=f"Recent reporting on {request.query}.",
                published_date="2024-03-20",
            ),
        ]
        return SearchResponse(
            search_id="srch_hermetic_01",
            session_id="sess_hermetic_01",
            results=results[: request.max_results],
            duration_ms=45,
        )

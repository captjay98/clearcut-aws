"""Parallel Search API Adapter."""
import logging
import os
import time

import httpx
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderFailure,
    ProviderResult,
    SearchResponse,
    SearchResultItem,
)
from clearcut.research.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)

PARALLEL_API_BASE_URL = os.getenv("PARALLEL_API_BASE_URL", "https://api.parallel.ai/v1")


class ParallelSearchAdapter(WebSearchPort):
    """Adapter for executing web search queries via the Parallel Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY", "")

    def search(self, request: SearchRequest) -> ProviderResult:
        """Execute real search against the live Parallel Search API."""
        start_time = time.monotonic()

        if not self.api_key:
            return ProviderFailure(
                kind="authentication",
                message="PARALLEL_API_KEY is not configured. Parallel Search requires an authentic API key.",
            )

        # Live Parallel Search API Call
        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "ClearCut-ResearchDesk/1.0",
            }
            # Parallel Search API contract: search_queries[] + optional objective.
            payload = {
                "search_queries": [request.query],
                "objective": getattr(
                    request,
                    "objective",
                    "screenplay pre-clearance source verification",
                ),
                "max_chars_total": getattr(request, "max_chars_total", 6000),
            }

            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{PARALLEL_API_BASE_URL}/search",
                    json=payload,
                    headers=headers,
                )

                if resp.status_code == 401 or resp.status_code == 403:
                    return ProviderFailure(
                        kind="authentication",
                        message="Parallel API Key authentication failed (HTTP 401/403)",
                    )

                if resp.status_code == 429:
                    return ProviderFailure(
                        kind="rate_limited",
                        message="Parallel API rate limit exceeded (HTTP 429)",
                    )

                if resp.is_error:
                    return ProviderFailure(
                        kind="retryable" if resp.status_code >= 500 else "permanent",
                        message=f"Parallel API error: HTTP {resp.status_code} - {resp.text}",
                    )

                data = resp.json()
                results = []
                for item in data.get("results", []):
                    # Contract returns excerpts[]; join into a single snippet.
                    excerpts = item.get("excerpts", [])
                    snippet = " … ".join(excerpts) if excerpts else item.get("snippet", "")
                    results.append(
                        SearchResultItem(
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            publisher=item.get("publisher", "Parallel Web Index"),
                            snippet=snippet,
                            published_date=item.get("publish_date"),
                        )
                    )

                return SearchResponse(
                    search_id=data.get("search_id", f"srch_{int(time.time())}"),
                    session_id=data.get("session_id", "sess_live"),
                    results=results,
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
        except Exception as exc:
            logger.warning(f"Parallel search request error: {exc}")
            return ProviderFailure(
                kind="retryable",
                message=f"Failed to reach Parallel API: {exc}",
            )

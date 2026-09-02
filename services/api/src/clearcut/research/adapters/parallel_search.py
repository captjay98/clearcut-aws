"""Parallel Search API adapter."""

import logging
import os
import time
from typing import Any

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
    """Execute web searches through the Parallel Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY", "")

    def search(self, request: SearchRequest) -> ProviderResult:
        """Execute one exact, persisted search query."""
        start_time = time.monotonic()

        if not self.api_key:
            return ProviderFailure(
                kind="authentication",
                message=(
                    "PARALLEL_API_KEY is not configured. Parallel Search requires "
                    "an authentic API key."
                ),
            )

        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "ClearCut-ResearchDesk/1.0",
                "X-ClearCut-Correlation-ID": str(request.correlation_id),
                "X-ClearCut-Research-Run-ID": str(request.research_run_id),
                "X-ClearCut-Research-Query-ID": str(request.research_query_id),
            }
            payload = {
                "search_queries": [request.query],
                "objective": request.objective,
                "max_chars_total": 6000,
            }

            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"{PARALLEL_API_BASE_URL}/search",
                    json=payload,
                    headers=headers,
                )

            if response.status_code in (401, 403):
                return ProviderFailure(
                    kind="authentication",
                    message="Parallel Search authentication failed.",
                )
            if response.status_code == 429:
                return ProviderFailure(
                    kind="rate_limited",
                    message="Parallel Search rate limit exceeded.",
                )
            if response.is_error:
                return ProviderFailure(
                    kind=("retryable" if response.status_code >= 500 else "permanent"),
                    message=f"Parallel Search failed with HTTP {response.status_code}.",
                )

            try:
                data: Any = response.json()
            except ValueError:
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Search returned an invalid response.",
                )

            if not isinstance(data, dict):
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Search returned an invalid response.",
                )

            search_id = data.get("search_id")
            session_id = data.get("session_id")
            if (
                not isinstance(search_id, str)
                or not search_id.strip()
                or not isinstance(session_id, str)
                or not session_id.strip()
            ):
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Search response omitted provider identity.",
                )

            raw_results = data.get("results", [])
            if not isinstance(raw_results, list):
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Search returned invalid results.",
                )

            results: list[SearchResultItem] = []
            for item in raw_results:
                if not isinstance(item, dict):
                    return ProviderFailure(
                        kind="invalid_response",
                        message="Parallel Search returned an invalid result item.",
                    )
                excerpts = item.get("excerpts", [])
                if not isinstance(excerpts, list):
                    excerpts = []
                snippet = (
                    " … ".join(str(excerpt) for excerpt in excerpts)
                    if excerpts
                    else str(item.get("snippet", ""))
                )
                results.append(
                    SearchResultItem(
                        url=str(item.get("url", "")),
                        title=str(item.get("title", "")),
                        publisher=str(item.get("publisher", "Parallel Web Index")),
                        snippet=snippet,
                        published_date=item.get("publish_date"),
                    )
                )

            return SearchResponse(
                search_id=search_id,
                session_id=session_id,
                results=results,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        except Exception:
            logger.warning("Parallel Search request failed.")
            return ProviderFailure(
                kind="retryable",
                message="Parallel Search request failed.",
            )

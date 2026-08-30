"""Parallel Extract API Adapter."""
import logging
import os
import time

import httpx
from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractRequest,
)
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort

logger = logging.getLogger(__name__)

PARALLEL_API_BASE_URL = os.getenv("PARALLEL_API_BASE_URL", "https://api.parallel.ai/v1")


class ParallelExtractAdapter(UrlExtractPort):
    """Adapter for extracting targeted, attributable content via the Parallel Extract API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY", "")

    def extract(self, request: ExtractRequest) -> ExtractResult:
        """Execute real extraction against the live Parallel Extract API."""
        if not self.api_key:
            return ProviderFailure(
                kind="authentication",
                message="PARALLEL_API_KEY is not configured. Parallel Extract requires an authentic API key.",
            )

        # Live Parallel Extract API Call
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "ClearCut-ResearchDesk/1.0",
            }
            payload = {
                "urls": list(request.urls),
                "objective": request.objective,
                "max_length": getattr(request, "max_length", 18000),
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{PARALLEL_API_BASE_URL}/extract",
                    json=payload,
                    headers=headers,
                )

                if resp.status_code == 401 or resp.status_code == 403:
                    return ProviderFailure(
                        kind="authentication",
                        message="Parallel API Key authentication failed (HTTP 401/403)",
                    )

                if resp.is_error:
                    return ProviderFailure(
                        kind="upstream_error",
                        message=f"Parallel Extract API error: HTTP {resp.status_code} - {resp.text}",
                    )

                data = resp.json()
                results = []
                for item in data.get("results", []):
                    results.append(
                        ExtractedPage(
                            url=item.get("url", ""),
                            title=item.get("title", ""),
                            content=item.get("content", item.get("text", "")),
                        )
                    )

                return ExtractBatchResponse(
                    extract_id=data.get("extract_id", f"ext_{int(time.time())}"),
                    session_id=request.session_id,
                    results=tuple(results),
                    errors=tuple(data.get("errors", [])),
                    warnings=tuple(data.get("warnings", [])),
                )
        except Exception as exc:
            logger.warning(f"Parallel extract request error: {exc}")
            return ProviderFailure(
                kind="network_error",
                message=f"Failed to reach Parallel API: {exc}",
            )

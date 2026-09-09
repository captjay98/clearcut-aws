"""Parallel Extract API adapter."""

import logging
import os
from typing import Any

import httpx
from clearcut.research.application.select_extract_targets import (
    canonicalize_https_url,
)
from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractedPageError,
    ExtractRequest,
)
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort

logger = logging.getLogger(__name__)

PARALLEL_API_BASE_URL = os.getenv("PARALLEL_API_BASE_URL", "https://api.parallel.ai/v1")
_MAX_EXCERPT_CHARS = 4000
_SAFE_ERROR_KINDS = frozenset(
    {"blocked", "not_found", "rate_limited", "timeout", "unavailable", "unknown"}
)
_SAFE_ERROR_MESSAGE = "Extraction failed for this URL."
_SAFE_WARNING_MESSAGE = "Parallel Extract returned provider warnings."


class ParallelExtractAdapter(UrlExtractPort):
    """Extract attributable content through the Parallel Extract API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY", "")

    def extract(self, request: ExtractRequest) -> ExtractResult:
        """Extract at most three Search-authorized URLs."""
        if not self.api_key:
            return ProviderFailure(
                kind="authentication",
                message=(
                    "PARALLEL_API_KEY is not configured. Parallel Extract requires "
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
                "X-ClearCut-Search-Attempt-ID": str(request.search_attempt_id),
            }
            payload = {
                "urls": list(request.urls),
                "objective": request.objective,
                "max_chars_total": 18000,
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{PARALLEL_API_BASE_URL}/extract",
                    json=payload,
                    headers=headers,
                )

            if response.status_code in (401, 403):
                return ProviderFailure(
                    kind="authentication",
                    message="Parallel Extract authentication failed.",
                )
            if response.status_code == 429:
                return ProviderFailure(
                    kind="rate_limited",
                    message="Parallel Extract rate limit exceeded.",
                )
            if response.is_error:
                return ProviderFailure(
                    kind=("retryable" if response.status_code >= 500 else "permanent"),
                    message=f"Parallel Extract failed with HTTP {response.status_code}.",
                )

            try:
                data: Any = response.json()
            except ValueError:
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Extract returned an invalid response.",
                )

            if not isinstance(data, dict):
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Extract returned an invalid response.",
                )

            extract_id = data.get("extract_id")
            if not isinstance(extract_id, str) or not extract_id.strip():
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Extract response omitted provider identity.",
                )

            # Parallel returns these keys with an explicit null rather than omitting
            # them, so `.get(key, [])` yields None and a plain isinstance check
            # rejects a perfectly valid response. Coalesce null to empty.
            raw_results = data.get("results") or []
            raw_errors = data.get("errors") or []
            raw_warnings = data.get("warnings") or []
            if not all(
                isinstance(value, list)
                for value in (raw_results, raw_errors, raw_warnings)
            ):
                return ProviderFailure(
                    kind="invalid_response",
                    message="Parallel Extract returned invalid result collections.",
                )

            requested_urls = {
                canonical_url
                for url in request.urls
                if (canonical_url := canonicalize_https_url(url)) is not None
            }
            results: list[ExtractedPage] = []
            seen_result_urls: set[str] = set()
            for item in raw_results:
                if not isinstance(item, dict):
                    return ProviderFailure(
                        kind="invalid_response",
                        message="Parallel Extract returned an invalid result item.",
                    )
                canonical_url = canonicalize_https_url(str(item.get("url", "")))
                if (
                    canonical_url is None
                    or canonical_url not in requested_urls
                    or canonical_url in seen_result_urls
                ):
                    return ProviderFailure(
                        kind="invalid_response",
                        message="Parallel Extract returned a result outside the request.",
                    )
                seen_result_urls.add(canonical_url)
                raw_excerpts = item.get("excerpts", [])
                excerpts = (
                    [
                        excerpt.strip()
                        for excerpt in raw_excerpts
                        if isinstance(excerpt, str) and excerpt.strip()
                    ]
                    if isinstance(raw_excerpts, list)
                    else []
                )
                content = " … ".join(excerpts)[:_MAX_EXCERPT_CHARS].rstrip()
                published_date = item.get("publish_date")
                results.append(
                    ExtractedPage(
                        url=canonical_url,
                        title=str(item.get("title", "")),
                        content=content,
                        published_date=(
                            published_date
                            if isinstance(published_date, str)
                            else None
                        ),
                    )
                )

            errors: list[ExtractedPageError] = []
            seen_error_urls: set[str] = set()
            for item in raw_errors:
                if not isinstance(item, dict):
                    return ProviderFailure(
                        kind="invalid_response",
                        message="Parallel Extract returned an invalid per-URL error.",
                    )
                canonical_url = canonicalize_https_url(str(item.get("url", "")))
                if (
                    canonical_url is None
                    or canonical_url not in requested_urls
                    or canonical_url in seen_error_urls
                ):
                    continue
                seen_error_urls.add(canonical_url)
                raw_kind = item.get("error_kind")
                error_kind = (
                    raw_kind.strip().lower()
                    if isinstance(raw_kind, str)
                    and raw_kind.strip().lower() in _SAFE_ERROR_KINDS
                    else "unknown"
                )
                errors.append(
                    ExtractedPageError(
                        url=canonical_url,
                        error_kind=error_kind,
                        message=_SAFE_ERROR_MESSAGE,
                    )
                )
                if len(errors) == len(requested_urls):
                    break

            return ExtractBatchResponse(
                extract_id=extract_id,
                session_id=request.session_id,
                results=tuple(results),
                errors=tuple(errors),
                warnings=((_SAFE_WARNING_MESSAGE,) if raw_warnings else ()),
            )
        except Exception:
            logger.warning("Parallel Extract request failed.")
            return ProviderFailure(
                kind="retryable",
                message="Parallel Extract request failed.",
            )

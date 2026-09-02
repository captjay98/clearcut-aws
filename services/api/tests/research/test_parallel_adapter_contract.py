from typing import Any
from uuid import UUID

import pytest
from clearcut.research.adapters import parallel_extract, parallel_search
from clearcut.research.adapters.parallel_extract import ParallelExtractAdapter
from clearcut.research.adapters.parallel_search import ParallelSearchAdapter
from clearcut.research.application.select_extract_targets import select_extract_targets
from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPageError,
    ExtractRequest,
)
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderFailure,
    SearchResponse,
    SearchResultItem,
)

CORRELATION_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8901")
RESEARCH_RUN_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8902")
RESEARCH_QUERY_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8903")
SEARCH_ATTEMPT_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8904")


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = "raw upstream body must never be exposed"
        self.is_error = status_code >= 400

    def json(self) -> dict[str, Any]:
        return self._payload


class RecordingClient:
    def __init__(self, response: FakeResponse, calls: list[dict[str, Any]]) -> None:
        self.response = response
        self.calls = calls

    def __enter__(self) -> "RecordingClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def _patch_client(monkeypatch: pytest.MonkeyPatch, module: Any, payload: dict[str, Any], status_code: int = 200) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    response = FakeResponse(payload, status_code=status_code)
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **_kwargs: RecordingClient(response, calls),
    )
    return calls


def test_parallel_search_sends_exact_persisted_query_and_correlation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_client(
        monkeypatch,
        parallel_search,
        {
            "search_id": "search-authentic-1",
            "session_id": "session-authentic-1",
            "results": [],
        },
    )
    request = SearchRequest(
        query="  exact persisted query  ",
        objective="Verify attributable ownership and current status for human review.",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
    )

    result = ParallelSearchAdapter(api_key="parallel-test-key").search(request)

    assert isinstance(result, SearchResponse)
    assert calls[0]["json"]["search_queries"] == ["  exact persisted query  "]
    assert calls[0]["json"]["objective"] == request.objective
    assert calls[0]["headers"]["X-ClearCut-Correlation-ID"] == str(CORRELATION_ID)
    assert calls[0]["headers"]["X-ClearCut-Research-Run-ID"] == str(RESEARCH_RUN_ID)
    assert calls[0]["headers"]["X-ClearCut-Research-Query-ID"] == str(RESEARCH_QUERY_ID)


@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "session-authentic-1", "results": []},
        {"search_id": "search-authentic-1", "results": []},
        {"search_id": "", "session_id": "session-authentic-1", "results": []},
    ],
)
def test_parallel_search_rejects_missing_or_blank_provider_identity(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    _patch_client(monkeypatch, parallel_search, payload)
    request = SearchRequest(
        query="persisted query",
        objective="Verify attributable ownership and current status for human review.",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
    )

    result = ParallelSearchAdapter(api_key="parallel-test-key").search(request)

    assert isinstance(result, ProviderFailure)
    assert result.kind == "invalid_response"
    assert "raw upstream" not in result.message


def test_parallel_search_redacts_upstream_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, parallel_search, {"secret": "provider-payload"}, status_code=503)
    request = SearchRequest(
        query="persisted query",
        objective="Verify attributable ownership and current status for human review.",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
    )

    result = ParallelSearchAdapter(api_key="parallel-test-key").search(request)

    assert isinstance(result, ProviderFailure)
    assert result.kind == "retryable"
    assert result.message == "Parallel Search failed with HTTP 503."


def test_parallel_extract_normalizes_per_url_errors_and_preserves_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_client(
        monkeypatch,
        parallel_extract,
        {
            "extract_id": "extract-authentic-1",
            "results": [],
            "errors": [
                {
                    "url": "https://example.com/failed",
                    "error_kind": "blocked",
                    "message": "Publisher blocked extraction",
                }
            ],
            "warnings": ["one page failed"],
        },
    )
    request = ExtractRequest(
        urls=["https://example.com/failed"],
        objective="Verify attributable ownership and current status for human review.",
        session_id="session-authentic-1",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
        search_attempt_id=SEARCH_ATTEMPT_ID,
    )

    result = ParallelExtractAdapter(api_key="parallel-test-key").extract(request)

    assert isinstance(result, ExtractBatchResponse)
    assert result.errors == (
        ExtractedPageError(
            url="https://example.com/failed",
            error_kind="blocked",
            message="Extraction failed for this URL.",
        ),
    )
    assert calls[0]["json"]["urls"] == ["https://example.com/failed"]
    assert calls[0]["headers"]["X-ClearCut-Correlation-ID"] == str(CORRELATION_ID)
    assert calls[0]["headers"]["X-ClearCut-Research-Run-ID"] == str(RESEARCH_RUN_ID)
    assert calls[0]["headers"]["X-ClearCut-Research-Query-ID"] == str(RESEARCH_QUERY_ID)
    assert calls[0]["headers"]["X-ClearCut-Search-Attempt-ID"] == str(SEARCH_ATTEMPT_ID)


def test_parallel_extract_rejects_missing_provider_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, parallel_extract, {"results": [], "errors": [], "warnings": []})
    request = ExtractRequest(
        urls=["https://example.com/source"],
        objective="Verify attributable ownership and current status for human review.",
        session_id="session-authentic-1",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
        search_attempt_id=SEARCH_ATTEMPT_ID,
    )

    result = ParallelExtractAdapter(api_key="parallel-test-key").extract(request)

    assert isinstance(result, ProviderFailure)
    assert result.kind == "invalid_response"


def test_extract_target_selection_canonicalizes_and_limits_https_urls() -> None:
    results = [
        SearchResultItem(
            url="https://Example.COM:443/path#fragment",
            title="First",
            publisher="Publisher",
            snippet="excerpt",
        ),
        SearchResultItem(
            url="https://example.com/path",
            title="Canonical duplicate",
            publisher="Publisher",
            snippet="excerpt",
        ),
        SearchResultItem(
            url="http://example.com/insecure",
            title="Insecure",
            publisher="Publisher",
            snippet="excerpt",
        ),
        *[
            SearchResultItem(
                url=f"https://example.com/source-{index}",
                title=f"Source {index}",
                publisher="Publisher",
                snippet="excerpt",
            )
            for index in range(1, 5)
        ],
    ]

    selected = select_extract_targets(results)

    assert selected == [
        "https://example.com/path",
        "https://example.com/source-1",
        "https://example.com/source-2",
    ]


def test_parallel_extract_ignores_full_bodies_and_redacts_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe_marker = "raw-provider-secret"
    _patch_client(
        monkeypatch,
        parallel_extract,
        {
            "extract_id": "extract-authentic-1",
            "results": [
                {
                    "url": "https://example.com/source",
                    "title": "Source",
                    "full_content": f"Full body {unsafe_marker}",
                    "excerpts": ["Attributable excerpt."],
                }
            ],
            "errors": [
                {
                    "url": "https://example.com/source",
                    "error_kind": "blocked",
                    "message": unsafe_marker,
                },
                {
                    "url": "https://example.com/source",
                    "error_kind": "timeout",
                    "message": unsafe_marker,
                },
                {
                    "url": "https://example.com/unrequested",
                    "error_kind": "blocked",
                    "message": unsafe_marker,
                },
            ],
            "warnings": [unsafe_marker],
        },
    )
    request = ExtractRequest(
        urls=["https://example.com/source"],
        objective="Verify attributable ownership and current status for human review.",
        session_id="session-authentic-1",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
        search_attempt_id=SEARCH_ATTEMPT_ID,
    )

    result = ParallelExtractAdapter(api_key="parallel-test-key").extract(request)

    assert isinstance(result, ExtractBatchResponse)
    assert result.results[0].content == "Attributable excerpt."
    assert result.errors == (
        ExtractedPageError(
            url="https://example.com/source",
            error_kind="blocked",
            message="Extraction failed for this URL.",
        ),
    )
    assert result.warnings == ("Parallel Extract returned provider warnings.",)
    assert unsafe_marker not in repr(result)

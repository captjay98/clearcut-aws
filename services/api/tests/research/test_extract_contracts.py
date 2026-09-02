from uuid import UUID

import pytest
from clearcut.research.domain.extraction import ExtractRequest
from pydantic import ValidationError

CORRELATION_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8911")
RESEARCH_RUN_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8912")
RESEARCH_QUERY_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8913")
SEARCH_ATTEMPT_ID = UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8914")


def _extract_request(urls: list[str]) -> ExtractRequest:
    return ExtractRequest(
        urls=urls,
        objective="Verify ownership and active trade status",
        session_id="sess_12345",
        correlation_id=CORRELATION_ID,
        research_run_id=RESEARCH_RUN_ID,
        research_query_id=RESEARCH_QUERY_ID,
        search_attempt_id=SEARCH_ATTEMPT_ID,
    )


def test_extract_request_validates_url_count_and_session() -> None:
    request = _extract_request(
        ["https://uspto.gov/trademarks/coca-cola", "https://cocacola.com/about"]
    )
    assert len(request.urls) == 2
    assert request.session_id == "sess_12345"

    with pytest.raises(ValidationError):
        _extract_request(
            [
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
                "https://example.com/4",
            ]
        )

    with pytest.raises(ValidationError):
        _extract_request([])

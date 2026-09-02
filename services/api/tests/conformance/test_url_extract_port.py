from uuid import UUID

from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractRequest


def test_hermetic_extract_returns_typed_batch() -> None:
    adapter = HermeticExtractAdapter()
    request = ExtractRequest(
        urls=["https://uspto.gov/tm1"],
        objective="Extract trademark details",
        session_id="sess_abc",
        correlation_id=UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8921"),
        research_run_id=UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8922"),
        research_query_id=UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8923"),
        search_attempt_id=UUID("018f62d0-7d57-7f31-b9c8-7f1504fc8924"),
    )

    result = adapter.extract(request)

    assert isinstance(result, ExtractBatchResponse)
    assert len(result.results) == 1
    assert result.results[0].url == "https://uspto.gov/tm1"
    assert len(result.results[0].content) <= 18000

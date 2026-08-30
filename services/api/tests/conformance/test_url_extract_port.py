from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractRequest


def test_hermetic_extract_returns_typed_batch():
    adapter = HermeticExtractAdapter()
    req = ExtractRequest(
        urls=["https://uspto.gov/tm1"],
        objective="Extract trademark details",
        session_id="sess_abc"
    )
    res = adapter.extract(req)
    assert isinstance(res, ExtractBatchResponse)
    assert len(res.results) == 1
    assert res.results[0].url == "https://uspto.gov/tm1"
    assert len(res.results[0].content) <= 18000

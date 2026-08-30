import pytest
from clearcut.research.domain.extraction import (
    ExtractRequest,
)
from pydantic import ValidationError


def test_extract_request_validates_url_count_and_session():
    # Valid request
    req = ExtractRequest(
        urls=["https://uspto.gov/trademarks/coca-cola", "https://cocacola.com/about"],
        objective="Verify ownership and active trade status",
        session_id="sess_12345"
    )
    assert len(req.urls) == 2
    assert req.session_id == "sess_12345"

    # Reject > 3 URLs
    with pytest.raises(ValidationError):
        ExtractRequest(
            urls=[
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
                "https://example.com/4",
            ],
            objective="Verify ownership",
            session_id="sess_12345"
        )

    # Reject 0 URLs
    with pytest.raises(ValidationError):
        ExtractRequest(
            urls=[],
            objective="Verify ownership",
            session_id="sess_12345"
        )

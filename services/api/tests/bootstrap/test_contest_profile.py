import pytest
from clearcut.bootstrap.production_manifest import (
    ContestProfileValidator,
    DisallowedProviderError,
)


def test_production_manifest_requires_approved_adapters():
    validator = ContestProfileValidator()

    valid_config = {
        "model_runtime": "GeminiAdkRuntime",
        "search_adapter": "ParallelSearchAdapter",
        "extract_adapter": "ParallelExtractAdapter",
        "monitor_adapter": "ParallelMonitorAdapter",
    }

    assert validator.validate_production_profile(valid_config) is True

def test_production_manifest_rejects_unapproved_ai_model():
    validator = ContestProfileValidator()

    invalid_config = {
        "model_runtime": "OpenAIAdapter",
        "search_adapter": "ParallelSearchAdapter",
        "extract_adapter": "ParallelExtractAdapter",
    }

    with pytest.raises(DisallowedProviderError, match="Unapproved model runtime"):
        validator.validate_production_profile(invalid_config)

def test_production_manifest_rejects_unapproved_search_provider():
    validator = ContestProfileValidator()

    invalid_config = {
        "model_runtime": "GeminiAdkRuntime",
        "search_adapter": "BingSearchAdapter",
        "extract_adapter": "ParallelExtractAdapter",
    }

    with pytest.raises(DisallowedProviderError, match="Unapproved search adapter"):
        validator.validate_production_profile(invalid_config)

import pytest
from clearcut.bootstrap.production_manifest import (
    ContestProfileValidator,
    DisallowedProviderError,
)

BASE_PROFILE = {
    "model_runtime": "GeminiAdkRuntime",
    "search_adapter": "ParallelSearchAdapter",
    "extract_adapter": "ParallelExtractAdapter",
    "monitor_adapter": "not-enabled",
    "monitor_decision": "NO-GO",
    "monitor_webhook_proof": "not-available",
}


def test_production_manifest_requires_exact_contest_adapters() -> None:
    validator = ContestProfileValidator()

    assert validator.validate_production_profile(BASE_PROFILE) is True


def test_production_manifest_rejects_non_adk_gemini_adapter() -> None:
    validator = ContestProfileValidator()
    invalid_config = {**BASE_PROFILE, "model_runtime": "VertexGeminiAdapter"}

    with pytest.raises(DisallowedProviderError, match="Unapproved model runtime"):
        validator.validate_production_profile(invalid_config)


def test_production_manifest_rejects_unapproved_ai_model() -> None:
    validator = ContestProfileValidator()
    invalid_config = {**BASE_PROFILE, "model_runtime": "OpenAIAdapter"}

    with pytest.raises(DisallowedProviderError, match="Unapproved model runtime"):
        validator.validate_production_profile(invalid_config)


def test_production_manifest_rejects_unapproved_search_provider() -> None:
    validator = ContestProfileValidator()
    invalid_config = {**BASE_PROFILE, "search_adapter": "BingSearchAdapter"}

    with pytest.raises(DisallowedProviderError, match="Unapproved search adapter"):
        validator.validate_production_profile(invalid_config)


def test_parallel_monitor_requires_go_decision_and_deployed_webhook_proof() -> None:
    validator = ContestProfileValidator()
    invalid_config = {
        **BASE_PROFILE,
        "monitor_adapter": "ParallelMonitorAdapter",
        "monitor_decision": "NO-GO",
        "monitor_webhook_proof": "not-available",
    }

    with pytest.raises(DisallowedProviderError, match="Monitor requires"):
        validator.validate_production_profile(invalid_config)


def test_parallel_monitor_is_allowed_only_with_recorded_go_and_proof() -> None:
    validator = ContestProfileValidator()
    proven_config = {
        **BASE_PROFILE,
        "monitor_adapter": "ParallelMonitorAdapter",
        "monitor_decision": "GO",
        "monitor_webhook_proof": "deployment-proof-018f0000",
    }

    assert validator.validate_production_profile(proven_config) is True

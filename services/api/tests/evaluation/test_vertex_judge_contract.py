import json
from dataclasses import fields
from types import SimpleNamespace
from uuid import uuid4

import pytest
from clearcut.ai.model_roles import GeminiRole, ModelRoleConfiguration
from clearcut.evaluation.adapters.vertex_judge import VertexJudgeAdapter
from clearcut.evaluation.domain.rubric import EvaluationStage, JudgeDimension
from clearcut.evaluation.ports.judge import (
    JudgeBindings,
    JudgeFailure,
    JudgeRequest,
    JudgeSuccess,
)


class FakeModels:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes) -> None:
        self.models = FakeModels(outcomes)


def _response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        text=json.dumps(payload),
        model_version="gemini-3.1-pro-preview-20260815",
        response_id="response-123",
        usage_metadata=SimpleNamespace(
            prompt_token_count=120,
            candidates_token_count=80,
            total_token_count=200,
        ),
    )


def _valid_payload() -> dict:
    eligible = {
        JudgeDimension.DETECTION_RECALL,
        JudgeDimension.APPROPRIATE_UNCERTAINTY,
        JudgeDimension.LEGAL_BOUNDARY,
        JudgeDimension.TOOL_EFFICIENCY,
    }
    return {
        "verdicts": [
            {
                "dimension": dimension.value,
                "status": "scored" if dimension in eligible else "not_applicable",
                "score": 90.0 if dimension in eligible else None,
                "rationale": (
                    "The supplied evaluation evidence supports this bounded score."
                    if dimension in eligible
                    else "This dimension is not evaluated during detection."
                ),
            }
            for dimension in JudgeDimension
        ],
        "critique": "Detection is well bounded but should retain explicit uncertainty.",
    }


def _request() -> JudgeRequest:
    return JudgeRequest(
        org_id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        stage=EvaluationStage.DETECTION,
        candidates=(),
        gate_results=(),
        bindings=JudgeBindings(
            rubric_version="rubric-2026-08-31",
            prompt_version="judge-prompt-v1",
            policy_version="org-policy-v1",
            input_sha256="a" * 64,
        ),
    )


def _configuration() -> ModelRoleConfiguration:
    return ModelRoleConfiguration(
        role=GeminiRole.JUDGE,
        model="gemini-3.1-pro-preview",
        environment_variable="CLEARCUT_GEMINI_JUDGE_MODEL",
        overridden=False,
    )


@pytest.mark.asyncio
async def test_vertex_judge_returns_closed_typed_verdicts_and_provider_metadata() -> None:
    client = FakeClient([_response(_valid_payload())])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        location="global",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeSuccess)
    assert len(result.verdicts) == 10
    assert {verdict.dimension for verdict in result.verdicts} == set(JudgeDimension)
    assert result.critique.startswith("Detection is well bounded")
    assert result.metadata.requested_model == "gemini-3.1-pro-preview"
    assert result.metadata.returned_model == "gemini-3.1-pro-preview-20260815"
    assert result.metadata.response_id == "response-123"
    assert result.metadata.usage.input_tokens == 120
    assert result.metadata.usage.output_tokens == 80
    assert result.metadata.usage.total_tokens == 200
    assert result.metadata.repair_count == 0
    assert result.metadata.latency_ms >= 0
    assert len(client.models.calls) == 1
    assert client.models.calls[0]["model"] == "gemini-3.1-pro-preview"
    assert {field.name for field in fields(JudgeSuccess)} == {
        "verdicts",
        "critique",
        "metadata",
    }


@pytest.mark.asyncio
async def test_vertex_judge_performs_at_most_one_same_model_repair() -> None:
    client = FakeClient(
        [
            _response({"verdicts": [], "critique": "incomplete"}),
            _response(_valid_payload()),
        ]
    )
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeSuccess)
    assert result.metadata.repair_count == 1
    assert len(client.models.calls) == 2
    assert [call["model"] for call in client.models.calls] == [
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview",
    ]


@pytest.mark.asyncio
async def test_vertex_judge_rejects_governed_mutations_and_stops_after_repair() -> None:
    invalid = _valid_payload() | {
        "decision": "cleared",
        "evidence_claim": {"text": "invented"},
        "policy_mutation": {"status": "active"},
    }
    client = FakeClient([_response(invalid), _response(invalid)])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    # A malformed/parse-rejected structured response is transient and retryable;
    # the adapter still redacts the offending content and stops after one repair.
    assert result.error.retryable is True
    assert "decision" not in result.error.message.lower()
    assert len(client.models.calls) == 2


@pytest.mark.asyncio
async def test_vertex_judge_normalizes_provider_failure_without_model_fallback() -> None:
    client = FakeClient([TimeoutError("raw provider detail must not escape")])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "provider_unavailable"
    assert result.error.message == "The judge provider could not complete the request."
    assert result.error.retryable is True
    assert result.requested_model == "gemini-3.1-pro-preview"
    assert len(client.models.calls) == 1
    assert client.models.calls[0]["model"] == "gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_vertex_judge_fails_when_provider_identity_metadata_is_missing() -> None:
    response = _response(_valid_payload())
    response.model_version = None
    client = FakeClient([response])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is False
    assert len(result.attempts) == 1
    assert len(client.models.calls) == 1


def test_judge_request_rejects_unknown_stage_before_provider_call() -> None:
    with pytest.raises(ValueError, match="Unknown evaluation stage"):
        JudgeRequest(
            org_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            stage="detectoin",
            candidates=(),
            gate_results=(),
            bindings=JudgeBindings(
                rubric_version="rubric-v1",
                prompt_version="prompt-v1",
                policy_version="policy-v1",
                input_sha256="e" * 64,
            ),
        )


@pytest.mark.asyncio
async def test_vertex_judge_rejects_failed_verdict_with_positive_score() -> None:
    invalid = _valid_payload()
    invalid["verdicts"][0]["status"] = "failed"
    invalid["verdicts"][0]["score"] = 95
    client = FakeClient([_response(invalid), _response(invalid)])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    assert len(client.models.calls) == 2


@pytest.mark.asyncio
async def test_vertex_judge_classifies_authentication_failure_as_non_retryable() -> None:
    unauthenticated_error = type("Unauthenticated", (Exception,), {})

    client = FakeClient([unauthenticated_error("raw credential detail")])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "provider_authentication_failed"
    assert result.error.retryable is False
    assert "credential" not in result.error.message.lower()


@pytest.mark.parametrize(
    ("field_name", "malformed_value"),
    [
        ("prompt_token_count", "not-an-integer"),
        ("total_token_count", -1),
    ],
)
@pytest.mark.asyncio
async def test_vertex_judge_normalizes_malformed_usage_metadata(
    field_name: str,
    malformed_value: object,
) -> None:
    response = _response(_valid_payload())
    setattr(response.usage_metadata, field_name, malformed_value)
    client = FakeClient([response])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is False
    assert len(client.models.calls) == 1


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, "invalid_request", False),
        (401, "provider_authentication_failed", False),
        (403, "provider_permission_denied", False),
        (429, "provider_rate_limited", True),
        (503, "provider_unavailable", True),
    ],
)
@pytest.mark.asyncio
async def test_vertex_judge_classifies_provider_status_codes_without_leaking_details(
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    from google.genai.errors import APIError

    client = FakeClient(
        [APIError(status_code, {"message": "raw provider secret", "status": "FAILED"})]
    )
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == expected_code
    assert result.error.retryable is retryable
    assert "secret" not in result.error.message.lower()


@pytest.mark.asyncio
async def test_vertex_judge_classifies_unknown_provider_failure_as_non_retryable() -> None:
    client = FakeClient([RuntimeError("raw unknown provider detail")])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "provider_error"
    assert result.error.retryable is False
    assert "unknown provider detail" not in result.error.message.lower()


@pytest.mark.parametrize(
    ("field_name", "malformed_value", "expected_model", "expected_response_id", "expected_usage"),
    [
        (
            "model_version",
            object(),
            None,
            "response-123",
            (120, 80, 200),
        ),
        (
            "response_id",
            object(),
            "gemini-3.1-pro-preview-20260815",
            None,
            (120, 80, 200),
        ),
        (
            "prompt_token_count",
            "invalid",
            "gemini-3.1-pro-preview-20260815",
            "response-123",
            (None, 80, 200),
        ),
        (
            "candidates_token_count",
            -1,
            "gemini-3.1-pro-preview-20260815",
            "response-123",
            (120, None, 200),
        ),
        (
            "total_token_count",
            True,
            "gemini-3.1-pro-preview-20260815",
            "response-123",
            (120, 80, None),
        ),
    ],
)
@pytest.mark.asyncio
async def test_vertex_judge_preserves_valid_sibling_metadata(
    field_name: str,
    malformed_value: object,
    expected_model: str | None,
    expected_response_id: str | None,
    expected_usage: tuple[int | None, int | None, int | None],
) -> None:
    response = _response(_valid_payload())
    target = response if field_name in {"model_version", "response_id"} else response.usage_metadata
    setattr(target, field_name, malformed_value)
    client = FakeClient([response])
    adapter = VertexJudgeAdapter(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await adapter.evaluate(_request())

    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.status == "invalid_response"
    assert attempt.returned_model == expected_model
    assert attempt.response_id == expected_response_id
    assert (
        attempt.usage.input_tokens,
        attempt.usage.output_tokens,
        attempt.usage.total_tokens,
    ) == expected_usage
    assert attempt.latency_ms >= 0
    assert attempt.error == result.error
    assert len(client.models.calls) == 1


def test_research_prompt_identifies_claims_as_the_response_under_review():
    from dataclasses import replace

    from clearcut.evaluation.ports.judge import ResearchEvidence

    request = replace(
        _request(),
        stage=EvaluationStage.RESEARCH,
        research_evidence=(
            ResearchEvidence(
                uuid4(),
                "https://example.com/source",
                "Publisher",
                "Source text",
                "primary",
                "supports",
                "A bounded supported claim",
            ),
        ),
    )
    contents = VertexJudgeAdapter._contents(request, repair=False)
    assert '"candidateResponse"' in contents
    assert "A bounded supported claim" in contents
    assert "empty detection candidates" in contents

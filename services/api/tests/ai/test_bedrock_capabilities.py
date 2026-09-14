"""Hermetic unit tests for all Bedrock capability adapters with fault injection."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from clearcut.detection.adapters.bedrock_runtime import BedrockDetectionAdapter
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.ports.model_runtime import DetectionFailure, DetectionSuccess
from clearcut.evaluation.adapters.bedrock_judge import BedrockJudgeAdapter
from clearcut.evaluation.domain.gates import GateResult, GateSeverity
from clearcut.evaluation.domain.rubric import DimensionStatus, EvaluationStage, JudgeDimension
from clearcut.evaluation.ports.judge import (
    JudgeBindings,
    JudgeFailure,
    JudgeRequest,
    JudgeSuccess,
)
from clearcut.research.adapters.bedrock_claim_synthesizer import BedrockClaimSynthesizer
from clearcut.research.adapters.bedrock_planner import BedrockResearchPlanner
from clearcut.research.domain.claims import EvidenceStance
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisFailure,
    ClaimSynthesisRequest,
    ClaimSynthesisSuccess,
)
from clearcut.research.ports.planner import (
    ResearchPlanningFailure,
    ResearchPlanningRequest,
    ResearchPlanningSuccess,
)
from clearcut.scripts.domain.elements import ScriptElement


class FakeBedrockClient:
    """Hermetic test double simulating Bedrock Converse API with queued outcomes."""

    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes: list[Any] = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise RuntimeError("FakeBedrockClient: No more outcomes queued.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _make_converse_response(
    text: str,
    *,
    model_id: str | None = None,
    request_id: str = "req-test-1",
    input_tokens: int = 120,
    output_tokens: int = 45,
    total_tokens: int = 165,
) -> dict[str, Any]:
    resp: dict[str, Any] = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": total_tokens,
        },
        "metrics": {"latencyMs": 150},
        "ResponseMetadata": {
            "RequestId": request_id,
            "HTTPStatusCode": 200,
            "HTTPHeaders": {},
        },
    }
    if model_id is not None:
        resp["additionalModelResponseFields"] = {"model": model_id}
        resp["ResponseMetadata"]["HTTPHeaders"]["x-amzn-bedrock-model-id"] = model_id
    return resp


def _make_element(text: str) -> ScriptElement:
    return ScriptElement.create(text=text)


# =========================================================================
# 1. Detection Adapter Tests
# =========================================================================


@pytest.mark.asyncio
async def test_bedrock_detection_success() -> None:
    element_text = "Bruce Wayne arrives at Wayne Enterprises in Gotham City."
    element = _make_element(element_text)

    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Wayne Enterprises",
                "span_start": 23,
                "span_end": 40,
                "rationale": "Commercial entity trademark requiring clearance.",
                "uncertainty": "low",
            }
        ]
    }
    raw_json = f"```json\n{json.dumps(payload)}\n```"
    canned_resp = _make_converse_response(
        raw_json,
        model_id="anthropic.claude-3-5-sonnet-20241022",
    )
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockDetectionAdapter(
        model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        client=fake_client,
    )

    assert adapter.requested_model == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    result = await adapter.detect_element(element)

    assert isinstance(result, DetectionSuccess)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.text == "Wayne Enterprises"
    assert cand.span_start == 23
    assert cand.span_end == 40
    assert cand.category == ClearanceCategory.PRODUCTS_AND_TRADEMARKS
    assert cand.uncertainty == "low"

    # Metadata assertions
    assert result.metadata.status == "succeeded"
    assert result.metadata.requested_model == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert result.metadata.returned_model == "anthropic.claude-3-5-sonnet-20241022"
    assert result.metadata.returned_model != adapter.requested_model  # Truthful!
    assert result.metadata.response_id == "req-test-1"
    assert result.metadata.usage.input_tokens == 120
    assert result.metadata.usage.output_tokens == 45
    assert result.metadata.usage.total_tokens == 165
    assert result.metadata.latency_ms >= 0


@pytest.mark.asyncio
async def test_bedrock_detection_truthful_returned_model_none_when_absent() -> None:
    element = _make_element("A red Ferrari speeds past.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Ferrari",
                "span_start": 6,
                "span_end": 13,
                "rationale": "Automotive brand trademark.",
                "uncertainty": "low",
            }
        ]
    }
    canned_resp = _make_converse_response(json.dumps(payload), model_id=None)
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockDetectionAdapter(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        client=fake_client,
    )

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    assert result.metadata.returned_model is None
    assert result.metadata.requested_model == "anthropic.claude-3-5-sonnet-20241022-v2:0"


@pytest.mark.asyncio
async def test_bedrock_detection_approximate_span_correction() -> None:
    element_text = "INT. WAYNE ENTERPRISES - DAY\nBruce Wayne sits quietly."
    element = _make_element(element_text)

    # Bedrock returned incorrect spans (0..11 instead of 5..22 for Wayne Enterprises)
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "WAYNE ENTERPRISES",
                "span_start": 0,
                "span_end": 17,
                "rationale": "Trademark entity.",
                "uncertainty": "low",
            }
        ]
    }
    canned_resp = _make_converse_response(json.dumps(payload))
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=fake_client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    cand = result.candidates[0]
    assert cand.text == "WAYNE ENTERPRISES"
    assert cand.span_start == 5
    assert cand.span_end == 22
    assert element_text[cand.span_start : cand.span_end] == "WAYNE ENTERPRISES"


@pytest.mark.asyncio
async def test_bedrock_detection_candidate_not_in_text_fails() -> None:
    element = _make_element("A quiet morning in Metropolis.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Wayne Enterprises",  # Not in Metropolis text
                "span_start": 0,
                "span_end": 17,
                "rationale": "Fictional corporation.",
                "uncertainty": "low",
            }
        ]
    }
    canned_resp = _make_converse_response(json.dumps(payload))
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=fake_client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.parametrize(
    ("client_error_code", "expected_domain_code", "expected_retryable"),
    [
        ("ThrottlingException", "provider_rate_limited", True),
        ("AccessDeniedException", "provider_permission_denied", False),
        ("ValidationException", "invalid_request", False),
        ("ModelTimeoutException", "provider_unavailable", True),
        ("ResourceNotFoundException", "provider_unavailable", False),
        ("InternalServerException", "provider_unavailable", True),
    ],
)
@pytest.mark.asyncio
async def test_bedrock_detection_error_mappings(
    client_error_code: str,
    expected_domain_code: str,
    expected_retryable: bool,
) -> None:
    element = _make_element("Some text.")
    error_response = {
        "Error": {"Code": client_error_code, "Message": "Error details"},
        "ResponseMetadata": {"HTTPStatusCode": 400 if client_error_code == "ValidationException" else 500},
    }
    exc = ClientError(error_response, "Converse")
    fake_client = FakeBedrockClient([exc])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=fake_client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == expected_domain_code
    assert result.error.retryable is expected_retryable
    assert result.attempt.status == "failed"


@pytest.mark.asyncio
async def test_bedrock_detection_timeout_error_mapping() -> None:
    element = _make_element("Some text.")
    exc = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")
    fake_client = FakeBedrockClient([exc])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=fake_client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "provider_unavailable"
    assert result.error.retryable is True


@pytest.mark.asyncio
async def test_bedrock_detection_malformed_json_refusal() -> None:
    element = _make_element("Some text.")
    canned_resp = _make_converse_response("I cannot fulfill this request due to policy.")
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=fake_client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


# =========================================================================
# 2. Research Planner Tests
# =========================================================================


@pytest.mark.asyncio
async def test_bedrock_planner_success() -> None:
    req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
        text="Wayne Enterprises",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    plan_payload = {
        "objective": "Verify trademark registrations and corporate entity status for Wayne Enterprises.",
        "search_queries": [
            "Wayne Enterprises trademark USPTO",
            "Wayne Enterprises corporate status",
        ],
    }
    canned_resp = _make_converse_response(
        json.dumps(plan_payload),
        model_id="anthropic.claude-3-haiku-20240307",
    )
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockResearchPlanner(
        model="anthropic.claude-3-haiku-20240307-v1:0",
        client=fake_client,
    )

    result = await adapter.plan_research(req)
    assert isinstance(result, ResearchPlanningSuccess)
    assert result.plan.objective == plan_payload["objective"]
    assert result.plan.search_queries == plan_payload["search_queries"]
    assert result.metadata.status == "succeeded"
    assert result.metadata.returned_model == "anthropic.claude-3-haiku-20240307"


@pytest.mark.asyncio
async def test_bedrock_planner_validation_failure() -> None:
    req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category="trademark",
        text="Wayne Enterprises",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    # Invalid: objective too short (< 20 chars), and only 1 search query (< 2)
    plan_payload = {
        "objective": "Too short",
        "search_queries": ["single query"],
    }
    canned_resp = _make_converse_response(json.dumps(plan_payload))
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockResearchPlanner(model="bedrock-model", client=fake_client)

    result = await adapter.plan_research(req)
    assert isinstance(result, ResearchPlanningFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


# =========================================================================
# 3. Claim Synthesizer Tests
# =========================================================================


@pytest.mark.asyncio
async def test_bedrock_claim_synthesizer_success() -> None:
    req = ClaimSynthesisRequest(
        item_id=uuid4(),
        snapshot_id=uuid4(),
        category="trademark",
        item_text="Wayne Enterprises",
        url="https://example.com/wayne",
        publisher="Example Corp",
        excerpt="Wayne Enterprises is registered as a Delaware corporation.",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    payload = {
        "claim_text": "Wayne Enterprises is registered as an active Delaware corporation.",
        "stance": "supports",
    }
    canned_resp = _make_converse_response(
        json.dumps(payload),
        model_id="anthropic.claude-3-haiku-20240307",
    )
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockClaimSynthesizer(model="bedrock-model", client=fake_client)

    result = await adapter.synthesize_claim(req)
    assert isinstance(result, ClaimSynthesisSuccess)
    assert result.claim_text == payload["claim_text"]
    assert result.stance == EvidenceStance.SUPPORTS
    assert result.metadata.status == "succeeded"
    assert result.metadata.returned_model == "anthropic.claude-3-haiku-20240307"


@pytest.mark.asyncio
async def test_bedrock_claim_synthesizer_invalid_stance() -> None:
    req = ClaimSynthesisRequest(
        item_id=uuid4(),
        snapshot_id=uuid4(),
        category="trademark",
        item_text="Wayne Enterprises",
        url="https://example.com",
        publisher="Pub",
        excerpt="Some excerpt.",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    payload = {
        "claim_text": "A valid claim sentence.",
        "stance": "unsupported_stance_enum_value",
    }
    canned_resp = _make_converse_response(json.dumps(payload))
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockClaimSynthesizer(model="bedrock-model", client=fake_client)

    result = await adapter.synthesize_claim(req)
    assert isinstance(result, ClaimSynthesisFailure)
    assert result.error.code == "invalid_response"


# =========================================================================
# 4. Judge Adapter & Repair Loop Tests
# =========================================================================


def _make_judge_request() -> JudgeRequest:
    return JudgeRequest(
        org_id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        stage=EvaluationStage.DETECTION,
        candidates=(),
        gate_results=(
            GateResult.create(
                candidate_id=uuid4(),
                gate_name="category_schema",
                passed=True,
                severity=GateSeverity.INFO,
                details="Passed",
            ),
        ),
        bindings=JudgeBindings(
            rubric_version="rubric_v1",
            prompt_version="prompt_v1",
            policy_version="policy_v1",
            input_sha256="a" * 64,
        ),
    )


def _make_valid_verdicts_payload() -> dict[str, Any]:
    # Stage DETECTION eligible dimensions:
    # DETECTION_RECALL, APPROPRIATE_UNCERTAINTY, LEGAL_BOUNDARY, TOOL_EFFICIENCY
    verdicts = []
    eligible_dims = {
        JudgeDimension.DETECTION_RECALL,
        JudgeDimension.APPROPRIATE_UNCERTAINTY,
        JudgeDimension.LEGAL_BOUNDARY,
        JudgeDimension.TOOL_EFFICIENCY,
    }
    for dim in JudgeDimension:
        if dim in eligible_dims:
            verdicts.append(
                {
                    "dimension": dim.value,
                    "status": DimensionStatus.SCORED.value,
                    "score": 90.0,
                    "rationale": f"Good performance on {dim.value}.",
                }
            )
        else:
            verdicts.append(
                {
                    "dimension": dim.value,
                    "status": DimensionStatus.NOT_APPLICABLE.value,
                    "score": None,
                    "rationale": f"Not applicable for detection stage {dim.value}.",
                }
            )
    return {
        "verdicts": verdicts,
        "critique": "Detection candidates adhere to rubric and legal boundary guidelines.",
    }


@pytest.mark.asyncio
async def test_bedrock_judge_success_on_first_attempt() -> None:
    req = _make_judge_request()
    payload = _make_valid_verdicts_payload()
    canned_resp = _make_converse_response(
        json.dumps(payload),
        model_id="anthropic.claude-3-5-sonnet-20241022",
    )
    fake_client = FakeBedrockClient([canned_resp])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=fake_client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeSuccess)
    assert len(result.verdicts) == len(JudgeDimension)
    assert result.critique == payload["critique"]
    assert result.metadata.repair_count == 0
    assert len(result.metadata.attempts) == 1
    assert result.metadata.attempts[0].status == "succeeded"
    assert result.metadata.returned_model == "anthropic.claude-3-5-sonnet-20241022"


@pytest.mark.asyncio
async def test_bedrock_judge_repair_loop_succeeds_on_second_attempt() -> None:
    req = _make_judge_request()
    valid_payload = _make_valid_verdicts_payload()

    # Attempt 1: malformed JSON
    resp1 = _make_converse_response("Malformed invalid JSON {not json}")
    # Attempt 2: valid JSON
    resp2 = _make_converse_response(json.dumps(valid_payload))

    fake_client = FakeBedrockClient([resp1, resp2])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=fake_client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeSuccess)
    assert result.metadata.repair_count == 1
    assert len(result.metadata.attempts) == 2
    assert result.metadata.attempts[0].status == "invalid_response"
    assert result.metadata.attempts[1].status == "succeeded"
    assert len(fake_client.calls) == 2
    # Verify second call includes repair prompt
    second_call_text = fake_client.calls[1]["messages"][0]["content"][0]["text"]
    assert "The previous response violated the required schema" in second_call_text


@pytest.mark.asyncio
async def test_bedrock_judge_double_failure_exhausts_repair() -> None:
    req = _make_judge_request()
    # Both attempts return malformed JSON
    resp1 = _make_converse_response("bad json 1")
    resp2 = _make_converse_response("bad json 2")

    fake_client = FakeBedrockClient([resp1, resp2])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=fake_client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert result.error.code == "invalid_response"
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "invalid_response"
    assert result.attempts[1].status == "invalid_response"


@pytest.mark.asyncio
async def test_bedrock_judge_invalid_bindings_rejected_without_calls() -> None:
    # Empty rubric_version violates bindings
    invalid_bindings = JudgeBindings(
        rubric_version="",
        prompt_version="prompt_v1",
        policy_version="policy_v1",
        input_sha256="abc1234567890",
    )
    req = JudgeRequest(
        org_id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        stage=EvaluationStage.DETECTION,
        candidates=(),
        gate_results=(),
        bindings=invalid_bindings,
    )
    fake_client = FakeBedrockClient([])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=fake_client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert result.attempts == ()
    assert len(fake_client.calls) == 0


@pytest.mark.asyncio
async def test_bedrock_judge_rubric_encoding_validation() -> None:
    req = _make_judge_request()
    invalid_payload = _make_valid_verdicts_payload()
    # Violate rule: numeric score alongside status "not_applicable"
    for v in invalid_payload["verdicts"]:
        if v["status"] == DimensionStatus.NOT_APPLICABLE.value:
            v["score"] = 42.0  # Illegal! Must be null
            break

    # Attempt 1 invalid, Attempt 2 valid
    resp1 = _make_converse_response(json.dumps(invalid_payload))
    valid_payload = _make_valid_verdicts_payload()
    resp2 = _make_converse_response(json.dumps(valid_payload))

    fake_client = FakeBedrockClient([resp1, resp2])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=fake_client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeSuccess)
    assert result.metadata.repair_count == 1

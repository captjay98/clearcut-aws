"""Adversarial stress-testing suite for Amazon Bedrock capability adapters.

Tests resilience against:
1. Malformed JSON payloads (truncated strings, markdown code fences with trailing garbage, unexpected JSON types).
2. Extreme and invalid span offsets in candidate detection (negative offsets, offsets exceeding text length, text not found in element).
3. Judge repair loop mechanics (single repair attempt on malformed response, success/failure transitions, attempt metadata recording, fault boundary).
4. Truthful returned_model (strict refusal to echo requested model when metadata is absent).
5. Simulated network, throttling, and permission faults (exact retryable flags and domain error mappings).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from botocore.exceptions import (
    ConnectionError as BotoConnectionError,
)
from clearcut.detection.adapters.bedrock_runtime import BedrockDetectionAdapter
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.ports.model_runtime import (
    DetectionFailure,
    DetectionSuccess,
)
from clearcut.evaluation.adapters.bedrock_judge import BedrockJudgeAdapter
from clearcut.evaluation.domain.gates import GateResult, GateSeverity
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    EvaluationStage,
    JudgeDimension,
)
from clearcut.evaluation.ports.judge import (
    JudgeBindings,
    JudgeFailure,
    JudgeRequest,
    JudgeSuccess,
)
from clearcut.research.adapters.bedrock_claim_synthesizer import BedrockClaimSynthesizer
from clearcut.research.adapters.bedrock_planner import BedrockResearchPlanner
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


class AdversarialBedrockClient:
    """Hermetic test double simulating Bedrock Converse API with inspection capabilities."""

    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes: list[Any] = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.outcomes:
            raise RuntimeError("AdversarialBedrockClient: No more outcomes queued.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _make_converse_resp(
    text: str,
    *,
    model_id: str | None = None,
    header_model_id: str | None = None,
    request_id: str = "req-adv-1",
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if header_model_id is not None:
        headers["x-amzn-bedrock-model-id"] = header_model_id
    elif model_id is not None:
        headers["x-amzn-bedrock-model-id"] = model_id

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
        "metrics": {"latencyMs": 120},
        "ResponseMetadata": {
            "RequestId": request_id,
            "HTTPStatusCode": 200,
            "HTTPHeaders": headers,
        },
    }
    if model_id is not None:
        resp["additionalModelResponseFields"] = {"model": model_id}
    return resp


def _make_client_error(code: str, http_status: int = 400) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": f"Simulated {code}"},
            "ResponseMetadata": {"HTTPStatusCode": http_status},
        },
        "Converse",
    )


def _make_valid_verdicts_payload() -> dict[str, Any]:
    eligible_dims = {
        JudgeDimension.DETECTION_RECALL,
        JudgeDimension.APPROPRIATE_UNCERTAINTY,
        JudgeDimension.LEGAL_BOUNDARY,
        JudgeDimension.TOOL_EFFICIENCY,
    }
    verdicts = []
    for dim in JudgeDimension:
        if dim in eligible_dims:
            verdicts.append(
                {
                    "dimension": dim.value,
                    "status": DimensionStatus.SCORED.value,
                    "score": 85.0,
                    "rationale": f"Valid score for {dim.value}.",
                }
            )
        else:
            verdicts.append(
                {
                    "dimension": dim.value,
                    "status": DimensionStatus.NOT_APPLICABLE.value,
                    "score": None,
                    "rationale": f"N/A for {dim.value}.",
                }
            )
    return {
        "verdicts": verdicts,
        "critique": "Solid evaluation meeting all legal and domain criteria.",
    }


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
            input_sha256="b" * 64,
        ),
    )


# =========================================================================
# Category 1: Malformed JSON Payloads
# =========================================================================


@pytest.mark.asyncio
async def test_malformed_json_truncated_strings_detection() -> None:
    """Verify DetectionAdapter handles truncated JSON without unhandled exceptions."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    truncated_raw = '{"candidates": [{"category": "products_and_trade'
    client = AdversarialBedrockClient([_make_converse_resp(truncated_raw)])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True
    assert result.attempt.status == "invalid_response"


@pytest.mark.asyncio
async def test_malformed_json_truncated_strings_planner() -> None:
    """Verify ResearchPlanner handles truncated JSON without crashing."""
    req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
        text="Wayne Enterprises",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    truncated_raw = '{"objective": "Plan source research for Wayne Enterprises'
    client = AdversarialBedrockClient([_make_converse_resp(truncated_raw)])
    adapter = BedrockResearchPlanner(model="bedrock-model", client=client)

    result = await adapter.plan_research(req)
    assert isinstance(result, ResearchPlanningFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.asyncio
async def test_malformed_json_truncated_strings_synthesizer() -> None:
    """Verify ClaimSynthesizer handles truncated JSON gracefully."""
    req = ClaimSynthesisRequest(
        item_id=uuid4(),
        snapshot_id=uuid4(),
        category="trademark",
        item_text="Wayne Enterprises",
        url="https://example.com",
        publisher="Test Publisher",
        excerpt="Wayne Enterprises was incorporated in 1939.",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    truncated_raw = '{"claim_text": "Wayne Enterprises was founded'
    client = AdversarialBedrockClient([_make_converse_resp(truncated_raw)])
    adapter = BedrockClaimSynthesizer(model="bedrock-model", client=client)

    result = await adapter.synthesize_claim(req)
    assert isinstance(result, ClaimSynthesisFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.asyncio
async def test_malformed_json_markdown_code_fences_with_trailing_garbage() -> None:
    """Verify JSON extraction succeeds when valid JSON is inside code fence with trailing commentary."""
    element = ScriptElement.create(text="Bruce Wayne visits Gotham.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.LOCATIONS_AND_LANDMARKS.value,
                "text": "Gotham",
                "span_start": 19,
                "span_end": 25,
                "rationale": "Fictional/real location reference.",
                "uncertainty": "low",
            }
        ]
    }
    raw_with_trailing = f"```json\n{json.dumps(payload)}\n```\nHere is some commentary after the closing fence."
    client = AdversarialBedrockClient([_make_converse_resp(raw_with_trailing)])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    assert len(result.candidates) == 1
    assert result.candidates[0].text == "Gotham"


@pytest.mark.asyncio
async def test_malformed_json_markdown_code_fences_robust_recovery_and_failure() -> None:
    """Verify that trailing commentary with unclosed brace still recovers valid JSON,
    while trailing commentary with corrupt closed braces gracefully fails as invalid_response.
    """
    element = ScriptElement.create(text="Bruce Wayne visits Gotham.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.LOCATIONS_AND_LANDMARKS.value,
                "text": "Gotham",
                "span_start": 19,
                "span_end": 25,
                "rationale": "Location",
                "uncertainty": "low",
            }
        ]
    }

    # Case A: Robust recovery - trailing commentary with unclosed brace
    raw_unclosed = f"```json\n{json.dumps(payload)}\n```\nExtra commentary: {{ unclosed brace "
    client_a = AdversarialBedrockClient([_make_converse_resp(raw_unclosed)])
    adapter_a = BedrockDetectionAdapter(model="bedrock-model", client=client_a)
    result_a = await adapter_a.detect_element(element)
    assert isinstance(result_a, DetectionSuccess)
    assert len(result_a.candidates) == 1

    # Case B: Graceful failure - trailing commentary with invalid closed braces spanning corrupt text
    raw_corrupt = f"```json\n{json.dumps(payload)}\n```\nExtra commentary with corrupt JSON: {{ 'invalid': key }} "
    client_b = AdversarialBedrockClient([_make_converse_resp(raw_corrupt)])
    adapter_b = BedrockDetectionAdapter(model="bedrock-model", client=client_b)
    result_b = await adapter_b.detect_element(element)
    assert isinstance(result_b, DetectionFailure)
    assert result_b.error.code == "invalid_response"
    assert result_b.error.retryable is True


@pytest.mark.parametrize(
    "unexpected_payload",
    [
        "12345",
        "true",
        "false",
        "null",
        '"just a plain string"',
        "[]",
        "[1, 2, 3]",
        '{"wrong_key": 42}',
        '{"candidates": "not a list"}',
        '{"candidates": [123, "string"]}',
        '{"candidates": [{"category": "unknown_category", "text": "text"}]}',
        "",
        "   \n\t  ",
    ],
)
@pytest.mark.asyncio
async def test_malformed_json_unexpected_types_detection(unexpected_payload: str) -> None:
    """Verify DetectionAdapter returns DetectionFailure without crashing on all unexpected JSON structures."""
    element = ScriptElement.create(text="Some screenplay element text.")
    client = AdversarialBedrockClient([_make_converse_resp(unexpected_payload)])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.parametrize(
    "unexpected_payload",
    [
        "12345",
        "true",
        "null",
        '"raw string"',
        '{"objective": 12345, "search_queries": ["query 1", "query 2"]}',
        '{"objective": "Valid length objective text goes here", "search_queries": "not a list"}',
        '{"objective": "Valid length objective text goes here", "search_queries": [123, 456]}',
        '{"objective": "Valid length objective text goes here", "search_queries": []}',
        '{"objective": "Valid length objective text goes here", "search_queries": ["q1", "q2", "q3", "q4"]}',
    ],
)
@pytest.mark.asyncio
async def test_malformed_json_unexpected_types_planner(unexpected_payload: str) -> None:
    """Verify ResearchPlanner rejects type-mismatched or schema-violating JSON payloads."""
    req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category="trademark",
        text="Wayne Enterprises",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    client = AdversarialBedrockClient([_make_converse_resp(unexpected_payload)])
    adapter = BedrockResearchPlanner(model="bedrock-model", client=client)

    result = await adapter.plan_research(req)
    assert isinstance(result, ResearchPlanningFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


# =========================================================================
# Category 2: Extreme and Invalid Span Offsets in Candidate Detection
# =========================================================================


@pytest.mark.parametrize(
    ("span_start", "span_end"),
    [
        (-1, 10),
        (-100, -10),
        (0, -5),
        (-1, -1),
    ],
)
@pytest.mark.asyncio
async def test_extreme_span_offsets_negative_offsets_fail_gracefully(
    span_start: int,
    span_end: int,
) -> None:
    """Verify negative span offsets fail gracefully as invalid_response without index errors."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.REAL_PERSONS_LIVING.value,
                "text": "Bruce Wayne",
                "span_start": span_start,
                "span_end": span_end,
                "rationale": "Character name clearance candidate.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.asyncio
async def test_extreme_span_offsets_exceeding_text_length_corrected_when_text_found() -> None:
    """Verify offsets exceeding element length are auto-corrected if candidate text is in element."""
    element_text = "A sleek Aston Martin DB5 roars past."
    element = ScriptElement.create(text=element_text)
    # Offsets 500..516 exceed element_text length (36 chars)
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Aston Martin DB5",
                "span_start": 500,
                "span_end": 516,
                "rationale": "Automotive vehicle trademark.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.text == "Aston Martin DB5"
    assert cand.span_start == 8
    assert cand.span_end == 24
    assert element_text[cand.span_start : cand.span_end] == "Aston Martin DB5"


@pytest.mark.asyncio
async def test_extreme_span_offsets_candidate_text_not_found_fails_gracefully() -> None:
    """Verify candidate text not in element fails as invalid_response without raising unhandled errors."""
    element = ScriptElement.create(text="Clark Kent walks down the street.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Wayne Enterprises",  # Absent from text
                "span_start": 500,
                "span_end": 517,
                "rationale": "Corporate trademark.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is True


@pytest.mark.parametrize(
    ("span_start", "span_end"),
    [
        (10, 5),   # Inverted
        (5, 5),    # Zero-length
        (100, 50), # Inverted large
    ],
)
@pytest.mark.asyncio
async def test_extreme_span_offsets_inverted_or_zero_length(
    span_start: int,
    span_end: int,
) -> None:
    """Verify inverted or zero-length offsets fail validation gracefully."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.REAL_PERSONS_LIVING.value,
                "text": "Bruce Wayne",
                "span_start": span_start,
                "span_end": span_end,
                "rationale": "Character name clearance.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"


@pytest.mark.parametrize(
    ("span_start", "span_end"),
    [
        (True, 10),      # bool is int subclass in Python
        (0, False),
        (1.5, 10.5),     # float
        ("0", "10"),     # string
        (None, 10),      # None
    ],
)
@pytest.mark.asyncio
async def test_extreme_span_offsets_non_integer_types(
    span_start: Any,
    span_end: Any,
) -> None:
    """Verify non-int span offsets (including Python bools) are rejected."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.REAL_PERSONS_LIVING.value,
                "text": "Bruce Wayne",
                "span_start": span_start,
                "span_end": span_end,
                "rationale": "Character name clearance.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"


@pytest.mark.asyncio
async def test_extreme_span_offsets_multibyte_unicode_handled() -> None:
    """Verify multibyte UTF-8 characters (emojis, accents) are handled accurately."""
    element_text = "SCENE 1: ☕ Batman stops at Café du Monde in Paris."
    element = ScriptElement.create(text=element_text)
    # Model returns wrong span (e.g. 0..10), but text "Café du Monde" is present
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.CORPORATE_ENTITIES.value,
                "text": "Café du Monde",
                "span_start": 0,
                "span_end": 13,
                "rationale": "Historic coffee establishment trademark.",
                "uncertainty": "low",
            }
        ]
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload))])
    adapter = BedrockDetectionAdapter(model="bedrock-model", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    cand = result.candidates[0]
    assert cand.text == "Café du Monde"
    assert element_text[cand.span_start : cand.span_end] == "Café du Monde"


# =========================================================================
# Category 3: Judge Repair Loop Mechanics
# =========================================================================


@pytest.mark.asyncio
async def test_judge_repair_loop_one_malformed_triggers_exactly_one_repair_and_succeeds() -> None:
    """Verify 1 malformed response triggers exactly 1 repair attempt and returns JudgeSuccess."""
    req = _make_judge_request()
    valid_payload = _make_valid_verdicts_payload()

    # Attempt 1: malformed string; Attempt 2: valid payload
    client = AdversarialBedrockClient([
        _make_converse_resp("Malformed JSON {broken"),
        _make_converse_resp(json.dumps(valid_payload)),
    ])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeSuccess)
    assert len(client.calls) == 2, "Expected exactly 2 client calls (1 initial + 1 repair)"
    assert result.metadata.repair_count == 1
    assert len(result.metadata.attempts) == 2

    # Attempt 1 must be recorded as invalid_response
    att1 = result.metadata.attempts[0]
    assert att1.ordinal == 1
    assert att1.status == "invalid_response"
    assert att1.error is not None
    assert att1.error.code == "invalid_response"

    # Attempt 2 must be recorded as succeeded
    att2 = result.metadata.attempts[1]
    assert att2.ordinal == 2
    assert att2.status == "succeeded"
    assert att2.error is None

    # Verify second call includes repair instruction
    second_prompt = client.calls[1]["messages"][0]["content"][0]["text"]
    assert "The previous response violated the required schema" in second_prompt


@pytest.mark.asyncio
async def test_judge_repair_loop_both_malformed_fails_with_both_attempts_recorded() -> None:
    """Verify when repair attempt also fails, JudgeFailure is returned with both attempts recorded."""
    req = _make_judge_request()

    client = AdversarialBedrockClient([
        _make_converse_resp("Attempt 1 malformed"),
        _make_converse_resp("Attempt 2 also malformed"),
    ])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert len(client.calls) == 2
    assert result.error.code == "invalid_response"
    assert len(result.attempts) == 2
    assert result.attempts[0].ordinal == 1
    assert result.attempts[0].status == "invalid_response"
    assert result.attempts[1].ordinal == 2
    assert result.attempts[1].status == "invalid_response"


@pytest.mark.asyncio
async def test_judge_repair_loop_network_fault_on_attempt1_does_not_trigger_repair() -> None:
    """Verify that network or throttling faults on attempt 1 do NOT trigger a repair attempt."""
    req = _make_judge_request()
    throttling_exc = _make_client_error("ThrottlingException", 429)

    client = AdversarialBedrockClient([throttling_exc])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert len(client.calls) == 1, "Must NOT invoke repair when call failed due to provider error"
    assert result.error.code == "provider_rate_limited"
    assert result.error.retryable is True
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "failed"


@pytest.mark.asyncio
async def test_judge_repair_loop_malformed_attempt1_then_network_fault_attempt2() -> None:
    """Verify when attempt 1 is malformed and attempt 2 encounters network fault, both are recorded."""
    req = _make_judge_request()
    timeout_exc = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")

    client = AdversarialBedrockClient([
        _make_converse_resp("Malformed JSON"),
        timeout_exc,
    ])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert len(client.calls) == 2
    assert result.error.code == "provider_unavailable"
    assert result.error.retryable is True
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "invalid_response"
    assert result.attempts[1].status == "failed"


@pytest.mark.asyncio
async def test_judge_repair_loop_negative_token_metadata_fails_without_repair() -> None:
    """Verify invalid token usage metadata triggers immediate failure without repair attempts."""
    req = _make_judge_request()
    # Negative input tokens is invalid metadata
    invalid_meta_resp = _make_converse_resp(
        json.dumps(_make_valid_verdicts_payload()),
        input_tokens=-10,
    )
    client = AdversarialBedrockClient([invalid_meta_resp])
    adapter = BedrockJudgeAdapter(model="bedrock-judge", client=client)

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeFailure)
    assert len(client.calls) == 1, "Metadata invalidity must not attempt repair"
    assert result.error.code == "invalid_response"
    assert result.error.retryable is False
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "invalid_response"


# =========================================================================
# Category 4: Truthful returned_model
# =========================================================================


@pytest.mark.asyncio
async def test_truthful_returned_model_omitted_returns_none_detection() -> None:
    """Verify BedrockDetectionAdapter returns None when response omits model metadata."""
    element = ScriptElement.create(text="A red Ferrari speeds past.")
    payload = {
        "candidates": [
            {
                "category": ClearanceCategory.PRODUCTS_AND_TRADEMARKS.value,
                "text": "Ferrari",
                "span_start": 6,
                "span_end": 13,
                "rationale": "Brand trademark.",
                "uncertainty": "low",
            }
        ]
    }
    # Response has no model in additionalModelResponseFields or HTTPHeaders
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(payload), model_id=None)])
    adapter = BedrockDetectionAdapter(
        model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        client=client,
    )

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    assert result.metadata.returned_model is None
    assert result.metadata.requested_model == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert result.metadata.returned_model != adapter.requested_model


@pytest.mark.asyncio
async def test_truthful_returned_model_omitted_returns_none_planner() -> None:
    """Verify BedrockResearchPlanner returns None when response omits model metadata."""
    req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category="trademark",
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
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(plan_payload), model_id=None)])
    adapter = BedrockResearchPlanner(
        model="us.anthropic.claude-3-haiku-20240307-v1:0",
        client=client,
    )

    result = await adapter.plan_research(req)
    assert isinstance(result, ResearchPlanningSuccess)
    assert result.metadata.returned_model is None
    assert result.metadata.requested_model == "us.anthropic.claude-3-haiku-20240307-v1:0"
    assert result.metadata.returned_model != adapter.requested_model


@pytest.mark.asyncio
async def test_truthful_returned_model_omitted_returns_none_synthesizer() -> None:
    """Verify BedrockClaimSynthesizer returns None when response omits model metadata."""
    req = ClaimSynthesisRequest(
        item_id=uuid4(),
        snapshot_id=uuid4(),
        category="trademark",
        item_text="Wayne Enterprises",
        url="https://example.com",
        publisher="Corp",
        excerpt="Wayne Enterprises was founded in 1939.",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    synth_payload = {
        "claim_text": "Wayne Enterprises is a corporation established in 1939.",
        "stance": "supports",
    }
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(synth_payload), model_id=None)])
    adapter = BedrockClaimSynthesizer(
        model="us.anthropic.claude-3-haiku-20240307-v1:0",
        client=client,
    )

    result = await adapter.synthesize_claim(req)
    assert isinstance(result, ClaimSynthesisSuccess)
    assert result.metadata.returned_model is None
    assert result.metadata.requested_model == "us.anthropic.claude-3-haiku-20240307-v1:0"
    assert result.metadata.returned_model != adapter.requested_model


@pytest.mark.asyncio
async def test_truthful_returned_model_omitted_returns_none_judge() -> None:
    """Verify BedrockJudgeAdapter returns None when response omits model metadata."""
    req = _make_judge_request()
    valid_payload = _make_valid_verdicts_payload()
    client = AdversarialBedrockClient([_make_converse_resp(json.dumps(valid_payload), model_id=None)])
    adapter = BedrockJudgeAdapter(
        model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        client=client,
    )

    result = await adapter.evaluate(req)
    assert isinstance(result, JudgeSuccess)
    assert result.metadata.returned_model is None
    assert result.metadata.requested_model == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert result.metadata.returned_model != adapter.requested_model
    assert result.metadata.attempts[0].returned_model is None


@pytest.mark.asyncio
async def test_truthful_returned_model_extracted_from_http_header_when_additional_fields_absent() -> None:
    """Verify model identity is extracted from HTTP header x-amzn-bedrock-model-id if present."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    payload = {"candidates": []}
    client = AdversarialBedrockClient([
        _make_converse_resp(
            json.dumps(payload),
            model_id=None,
            header_model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        )
    ])
    adapter = BedrockDetectionAdapter(model="requested-alias", client=client)

    result = await adapter.detect_element(element)
    assert isinstance(result, DetectionSuccess)
    assert result.metadata.returned_model == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert result.metadata.requested_model == "requested-alias"


# =========================================================================
# Category 5: Simulated Network/Throttling Faults & Retryable Flags
# =========================================================================


@pytest.mark.parametrize(
    ("client_error_code", "http_status", "expected_domain_code", "expected_retryable"),
    [
        ("ThrottlingException", 429, "provider_rate_limited", True),
        ("RequestLimitExceeded", 429, "provider_rate_limited", True),
        ("TooManyRequestsException", 429, "provider_rate_limited", True),
        ("AccessDeniedException", 403, "provider_permission_denied", False),
        ("AuthFailure", 403, "provider_permission_denied", False),
        ("UnrecognizedClientException", 403, "provider_permission_denied", False),
        ("ValidationException", 400, "invalid_request", False),
        ("ModelTimeoutException", 503, "provider_unavailable", True),
        ("ServiceUnavailableException", 503, "provider_unavailable", True),
        ("InternalServerException", 500, "provider_unavailable", True),
        ("ModelNotReadyException", 503, "provider_unavailable", True),
        ("ModelErrorException", 500, "provider_unavailable", True),
        ("ResourceNotFoundException", 404, "provider_unavailable", False),
        ("UnknownServerError", 502, "provider_unavailable", True),
        ("GatewayTimeout", 504, "provider_unavailable", True),
    ],
)
@pytest.mark.asyncio
async def test_simulated_client_error_codes_across_adapters(
    client_error_code: str,
    http_status: int,
    expected_domain_code: str,
    expected_retryable: bool,
) -> None:
    """Verify botocore ClientErrors map to exact domain codes and retryable flags across adapters."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    client_err = _make_client_error(client_error_code, http_status)

    # 1. Detection
    det_client = AdversarialBedrockClient([client_err])
    det_adapter = BedrockDetectionAdapter(model="bedrock-model", client=det_client)
    det_res = await det_adapter.detect_element(element)
    assert isinstance(det_res, DetectionFailure)
    assert det_res.error.code == expected_domain_code
    assert det_res.error.retryable is expected_retryable

    # 2. Planner
    plan_client = AdversarialBedrockClient([client_err])
    plan_adapter = BedrockResearchPlanner(model="bedrock-model", client=plan_client)
    plan_req = ResearchPlanningRequest(
        item_id=uuid4(),
        version_id=uuid4(),
        category="trademark",
        text="Wayne",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    plan_res = await plan_adapter.plan_research(plan_req)
    assert isinstance(plan_res, ResearchPlanningFailure)
    assert plan_res.error.code == expected_domain_code
    assert plan_res.error.retryable is expected_retryable

    # 3. Synthesizer
    synth_client = AdversarialBedrockClient([client_err])
    synth_adapter = BedrockClaimSynthesizer(model="bedrock-model", client=synth_client)
    synth_req = ClaimSynthesisRequest(
        item_id=uuid4(),
        snapshot_id=uuid4(),
        category="trademark",
        item_text="Wayne",
        url="https://example.com",
        publisher="P",
        excerpt="Excerpt",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )
    synth_res = await synth_adapter.synthesize_claim(synth_req)
    assert isinstance(synth_res, ClaimSynthesisFailure)
    assert synth_res.error.code == expected_domain_code
    assert synth_res.error.retryable is expected_retryable

    # 4. Judge
    judge_client = AdversarialBedrockClient([client_err])
    judge_adapter = BedrockJudgeAdapter(model="bedrock-model", client=judge_client)
    judge_res = await judge_adapter.evaluate(_make_judge_request())
    assert isinstance(judge_res, JudgeFailure)
    assert judge_res.error.code == expected_domain_code
    assert judge_res.error.retryable is expected_retryable


@pytest.mark.parametrize(
    "network_exc",
    [
        ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com"),
        ConnectTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com"),
        EndpointConnectionError(endpoint_url="https://bedrock.us-east-1.amazonaws.com"),
        BotoConnectionError(error="connection lost"),
        TimeoutError("asyncio timeout"),
        ConnectionError("connection reset by peer"),
    ],
)
@pytest.mark.asyncio
async def test_simulated_network_faults_across_adapters(network_exc: Exception) -> None:
    """Verify network connection and timeout exceptions map to provider_unavailable with retryable=True."""
    element = ScriptElement.create(text="Bruce Wayne enters.")

    # Detection
    det_client = AdversarialBedrockClient([network_exc])
    det_adapter = BedrockDetectionAdapter(model="bedrock-model", client=det_client)
    det_res = await det_adapter.detect_element(element)
    assert isinstance(det_res, DetectionFailure)
    assert det_res.error.code == "provider_unavailable"
    assert det_res.error.retryable is True

    # Judge
    judge_client = AdversarialBedrockClient([network_exc])
    judge_adapter = BedrockJudgeAdapter(model="bedrock-model", client=judge_client)
    judge_res = await judge_adapter.evaluate(_make_judge_request())
    assert isinstance(judge_res, JudgeFailure)
    assert judge_res.error.code == "provider_unavailable"
    assert judge_res.error.retryable is True


@pytest.mark.asyncio
async def test_unhandled_runtime_error_maps_to_non_retryable_provider_error() -> None:
    """Verify unexpected runtime exceptions map to provider_error with retryable=False."""
    element = ScriptElement.create(text="Bruce Wayne enters.")
    runtime_exc = RuntimeError("Unexpected runtime failure inside client")

    det_client = AdversarialBedrockClient([runtime_exc])
    det_adapter = BedrockDetectionAdapter(model="bedrock-model", client=det_client)
    det_res = await det_adapter.detect_element(element)
    assert isinstance(det_res, DetectionFailure)
    assert det_res.error.code == "provider_error"
    assert det_res.error.retryable is False

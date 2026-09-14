"""Amazon Bedrock Converse judge adapter with closed structured output and repair loop."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from clearcut.ai.adapters.bedrock_base import (
    classify_bedrock_error,
    elapsed_ms,
    extract_converse_text,
    extract_json_payload,
    extract_response_id,
    extract_returned_model,
    extract_token_usage,
    invoke_bedrock_converse,
)
from clearcut.ai.model_roles import (
    BedrockRole,
    ModelRoleConfiguration,
    resolve_bedrock_role,
)
from clearcut.bootstrap.paid_providers import PaidProviderGate
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    EvaluationStage,
    JudgeDimension,
    JudgeVerdict,
    get_stage_eligible_dimensions,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeFailure,
    JudgeInvocationMetadata,
    JudgePort,
    JudgeRequest,
    JudgeResult,
    JudgeSafeError,
    JudgeSuccess,
    TokenUsage,
    validate_judge_bindings,
)

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are ClearCut's evaluation judge. Score only the supplied rubric dimensions "
    "from the supplied candidates and deterministic gate results. Return concise "
    "scores, rationales, and critique using the exact JSON schema: "
    '{"verdicts": [{"dimension": str, "status": str, "score": number|null, "rationale": str}], "critique": str}. '
    "Preserve explicit uncertainty and pre-clearance legal boundaries. Never create a clearance decision, "
    "evidence claim, policy change, disposition, or legal conclusion. Do not provide hidden reasoning.\n\n"
    "Encoding rules, which are validated strictly and must be followed exactly:\n"
    "1. Return exactly one verdict for every dimension in the schema enum, with no duplicates and none omitted.\n"
    '2. For any dimension absent from eligibleDimensions, set status to "not_applicable" and score to null.\n'
    '3. For an eligible dimension, use status "scored" with a numeric score between 0 and 100, or status "failed" '
    'with a score of exactly 0, or status "incomplete" with score null.\n'
    '4. Never supply a numeric score alongside status "not_applicable" or "incomplete".\n'
    "5. Every rationale must be a non-empty string of at most 2000 characters, and the critique must be a non-empty string of at most 2000 characters."
)
_EMPTY_USAGE = TokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


class _InvalidJudgeResponseError(ValueError):
    pass


class BedrockJudgeAdapter(JudgePort):
    """Amazon Bedrock implementation of JudgePort with a bounded repair loop."""

    def __init__(
        self,
        *,
        model: str,
        region: str = "us-east-1",
        role_configuration: ModelRoleConfiguration | None = None,
        client: Any | None = None,
        gate: PaidProviderGate | None = None,
    ) -> None:
        self._model = model
        self._region = region
        self._role_configuration = role_configuration or resolve_bedrock_role(
            BedrockRole.JUDGE
        )
        self._client = client
        self._gate = gate

    @property
    def requested_model(self) -> str:
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
                config=Config(retries={"total_max_attempts": 2}),
            )
        return self._client

    async def evaluate(self, request: JudgeRequest) -> JudgeResult:
        request_error = validate_judge_bindings(request.bindings)
        if request_error is not None:
            return JudgeFailure(
                error=request_error,
                requested_model=self._model,
                attempts=(),
            )

        attempts: list[JudgeAttemptMetadata] = []
        total_latency_ms = 0

        for repair_count in range(2):
            started = time.perf_counter()
            content = self._contents(request, repair=repair_count == 1)
            messages = [{"role": "user", "content": [{"text": content}]}]
            system = [{"text": _SYSTEM_INSTRUCTION}]

            try:
                client = self._get_client()
                if self._gate is not None:
                    async with self._gate.acquire("bedrock"):
                        response = await invoke_bedrock_converse(
                            client,
                            model_id=self._model,
                            messages=messages,
                            system=system,
                        )
                else:
                    response = await invoke_bedrock_converse(
                        client,
                        model_id=self._model,
                        messages=messages,
                        system=system,
                    )
            except Exception as provider_exception:
                latency_ms = elapsed_ms(started)
                error = classify_bedrock_error(provider_exception, JudgeSafeError)
                attempts.append(
                    JudgeAttemptMetadata(
                        ordinal=repair_count + 1,
                        status="failed",
                        returned_model=None,
                        response_id=None,
                        usage=_EMPTY_USAGE,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                return JudgeFailure(
                    error=error,
                    requested_model=self._model,
                    attempts=tuple(attempts),
                )

            latency_ms = elapsed_ms(started)
            total_latency_ms += latency_ms
            usage, metadata_invalid = extract_token_usage(response, TokenUsage)
            returned_model = extract_returned_model(response)
            response_id = extract_response_id(response)

            if metadata_invalid:
                error = JudgeSafeError(
                    code="invalid_response",
                    message="The judge provider returned invalid response metadata.",
                    retryable=False,
                )
                attempts.append(
                    JudgeAttemptMetadata(
                        ordinal=repair_count + 1,
                        status="invalid_response",
                        returned_model=returned_model,
                        response_id=response_id,
                        usage=usage,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                return JudgeFailure(
                    error=error,
                    requested_model=self._model,
                    attempts=tuple(attempts),
                )

            try:
                raw_text = extract_converse_text(response)
                verdicts, critique = self._parse_response(request, raw_text)
            except _InvalidJudgeResponseError:
                error = JudgeSafeError(
                    code="invalid_response",
                    message="The judge provider returned an invalid structured response.",
                    retryable=True,
                )
                attempts.append(
                    JudgeAttemptMetadata(
                        ordinal=repair_count + 1,
                        status="invalid_response",
                        returned_model=returned_model,
                        response_id=response_id,
                        usage=usage,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                if repair_count == 0:
                    continue
                return JudgeFailure(
                    error=error,
                    requested_model=self._model,
                    attempts=tuple(attempts),
                )

            attempts.append(
                JudgeAttemptMetadata(
                    ordinal=repair_count + 1,
                    status="succeeded",
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=latency_ms,
                    error=None,
                )
            )
            return JudgeSuccess(
                verdicts=verdicts,
                critique=critique,
                metadata=JudgeInvocationMetadata(
                    requested_model=self._model,
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=total_latency_ms,
                    repair_count=repair_count,
                    attempts=tuple(attempts),
                ),
            )

        raise RuntimeError("Judge repair bound was exceeded.")

    @staticmethod
    def _contents(request: JudgeRequest, *, repair: bool) -> str:
        payload = {
            "stage": request.stage,
            "bindings": {
                "rubricVersion": request.bindings.rubric_version,
                "promptVersion": request.bindings.prompt_version,
                "policyVersion": request.bindings.policy_version,
                "inputSha256": request.bindings.input_sha256,
            },
            "eligibleDimensions": sorted(
                dimension.value for dimension in get_stage_eligible_dimensions(request.stage)
            ),
            "candidates": [
                {
                    "category": candidate.category.value,
                    "elementId": str(candidate.element_id),
                    "spanStart": candidate.span_start,
                    "spanEnd": candidate.span_end,
                    "text": candidate.text,
                    "rationale": candidate.rationale,
                    "uncertainty": candidate.uncertainty,
                }
                for candidate in request.candidates
            ],
            "gateResults": [
                {
                    "gateName": gate.gate_name,
                    "passed": gate.passed,
                    "severity": gate.severity.value,
                    "details": gate.details,
                }
                for gate in request.gate_results
            ],
            "researchEvidence": [
                {
                    "snapshotId": str(evidence.snapshot_id),
                    "url": evidence.url,
                    "publisher": evidence.publisher,
                    "excerpt": evidence.excerpt,
                    "authorityTier": evidence.authority_tier,
                    "stance": evidence.stance,
                    "claimText": evidence.claim_text,
                }
                for evidence in request.research_evidence
            ],
        }
        if request.stage is EvaluationStage.RESEARCH:
            payload["candidateResponse"] = [
                {
                    "claimText": evidence.claim_text,
                    "snapshotId": str(evidence.snapshot_id),
                    "url": evidence.url,
                    "stance": evidence.stance,
                }
                for evidence in request.research_evidence
            ]
            payload["evaluationContext"] = (
                "Research claim evaluation: candidateResponse contains the generated claims "
                "under review. researchEvidence contains their attributable source excerpts. "
                "The empty detection candidates list is expected at this stage and does not "
                "mean the candidate response is missing. Evaluate grounding, citations, "
                "conflicts, uncertainty, and legal boundaries against these supplied claims "
                "and sources. Keep incomplete or failed verdicts when the actual supplied "
                "claims or sources do not support evaluation; never invent missing facts."
            )
        instruction = (
            "The previous response violated the required schema. Return one corrected "
            "response only; use the same evidence and do not add facts."
            if repair
            else "Evaluate the supplied snapshot using the exact response schema."
        )
        return f"{instruction}\n{json.dumps(payload, sort_keys=True)}"

    def _parse_response(
        self,
        request: JudgeRequest,
        raw_text: str,
    ) -> tuple[tuple[JudgeVerdict, ...], str]:
        try:
            payload = extract_json_payload(raw_text)
        except (ValueError, json.JSONDecodeError, TypeError) as error:
            raise _InvalidJudgeResponseError from error

        if not isinstance(payload, dict) or set(payload) != {"verdicts", "critique"}:
            raise _InvalidJudgeResponseError
        critique = payload["critique"]
        raw_verdicts = payload["verdicts"]
        if (
            not isinstance(critique, str)
            or not critique.strip()
            or len(critique) > 2000
            or not isinstance(raw_verdicts, list)
            or len(raw_verdicts) != len(JudgeDimension)
        ):
            raise _InvalidJudgeResponseError

        eligible = get_stage_eligible_dimensions(request.stage)
        verdicts: list[JudgeVerdict] = []
        seen: set[JudgeDimension] = set()

        for raw_verdict in raw_verdicts:
            if not isinstance(raw_verdict, dict) or set(raw_verdict) != {
                "dimension",
                "status",
                "score",
                "rationale",
            }:
                raise _InvalidJudgeResponseError
            try:
                dimension = JudgeDimension(raw_verdict["dimension"])
                status = DimensionStatus(raw_verdict["status"])
            except (TypeError, ValueError) as error:
                raise _InvalidJudgeResponseError from error

            if dimension in seen:
                raise _InvalidJudgeResponseError
            seen.add(dimension)

            score = raw_verdict["score"]
            rationale = raw_verdict["rationale"]
            if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 2000:
                raise _InvalidJudgeResponseError
            if isinstance(score, bool) or (
                score is not None and not isinstance(score, (int, float))
            ):
                raise _InvalidJudgeResponseError

            normalized_score = float(score) if score is not None else None
            if normalized_score is not None and not 0 <= normalized_score <= 100:
                raise _InvalidJudgeResponseError
            if status is DimensionStatus.SCORED and normalized_score is None:
                raise _InvalidJudgeResponseError
            if (
                status in {DimensionStatus.INCOMPLETE, DimensionStatus.NOT_APPLICABLE}
                and normalized_score is not None
            ):
                raise _InvalidJudgeResponseError
            if status is DimensionStatus.FAILED and normalized_score != 0.0:
                raise _InvalidJudgeResponseError
            if dimension not in eligible and status is not DimensionStatus.NOT_APPLICABLE:
                raise _InvalidJudgeResponseError

            verdicts.append(
                JudgeVerdict.create(
                    dimension=dimension,
                    status=status,
                    score=normalized_score,
                    rationale=rationale,
                )
            )

        if seen != set(JudgeDimension):
            raise _InvalidJudgeResponseError
        return tuple(verdicts), critique.strip()

"""Vertex Gemini Pro judge with closed structured output and one repair maximum."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfiguration,
    resolve_model_role,
)
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

_SYSTEM_INSTRUCTION = (
    "You are ClearCut's evaluation judge. Score only the supplied rubric dimensions "
    "from the supplied candidates and deterministic gate results. Return concise "
    "scores, rationales, and critique using the exact JSON schema. Preserve explicit "
    "uncertainty and pre-clearance legal boundaries. Never create a clearance decision, "
    "evidence claim, policy change, disposition, or legal conclusion. Do not provide "
    "hidden reasoning or chain-of-thought."
    "\n\n"
    "Encoding rules, which are validated strictly and must be followed exactly:\n"
    "1. Return exactly one verdict for every dimension in the schema enum, with no "
    "duplicates and none omitted.\n"
    "2. For any dimension absent from eligibleDimensions, set status to "
    '"not_applicable" and score to null.\n'
    '3. For an eligible dimension, use status "scored" with a numeric score between '
    '0 and 100, or status "failed" with a score of exactly 0, or status "incomplete" '
    "with score null.\n"
    '4. Never supply a numeric score alongside status "not_applicable" or '
    '"incomplete".\n'
    "5. Every rationale must be a non-empty string of at most 2000 characters, and the "
    "critique must be a non-empty string of at most 2000 characters."
)

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdicts": {
            "type": "ARRAY",
            "minItems": 10,
            "maxItems": 10,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "dimension": {
                        "type": "STRING",
                        "enum": [dimension.value for dimension in JudgeDimension],
                    },
                    "status": {
                        "type": "STRING",
                        "enum": [status.value for status in DimensionStatus],
                    },
                    "score": {
                        "anyOf": [
                            {"type": "NUMBER", "minimum": 0, "maximum": 100},
                            {"type": "NULL"},
                        ]
                    },
                    "rationale": {"type": "STRING", "maxLength": 2000},
                },
                "required": ["dimension", "status", "score", "rationale"],
            },
        },
        "critique": {"type": "STRING", "maxLength": 2000},
    },
    "required": ["verdicts", "critique"],
}

_EMPTY_USAGE = TokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


class _InvalidJudgeResponseError(ValueError):
    pass


class VertexJudgeAdapter(JudgePort):
    def __init__(
        self,
        *,
        project: str,
        location: str = "global",
        role_configuration: ModelRoleConfiguration | None = None,
        client: Any | None = None,
    ) -> None:
        self.project = project
        self.location = location
        self.role_configuration = role_configuration or resolve_model_role(GeminiRole.JUDGE)
        if self.role_configuration.role is not GeminiRole.JUDGE:
            raise ValueError("VertexJudgeAdapter requires the judge model role.")
        self.model = self.role_configuration.model
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client

    @property
    def requested_model(self) -> str:
        return self.model

    async def evaluate(self, request: JudgeRequest) -> JudgeResult:
        request_error = self._validate_request(request)
        if request_error is not None:
            return JudgeFailure(
                error=request_error,
                requested_model=self.model,
                attempts=(),
            )

        attempts: list[JudgeAttemptMetadata] = []
        total_latency_ms = 0
        for repair_count in range(2):
            started = time.perf_counter()
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self.model,
                    contents=self._contents(request, repair=repair_count == 1),
                    config=self._generate_content_config(),
                )
            except Exception as provider_exception:
                latency_ms = self._elapsed_ms(started)
                error = self._classify_provider_error(provider_exception)
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
                    requested_model=self.model,
                    attempts=tuple(attempts),
                )

            latency_ms = self._elapsed_ms(started)
            total_latency_ms += latency_ms
            usage, metadata_invalid = self._usage(response)
            try:
                returned_model = self._optional_string(getattr(response, "model_version", None))
            except ValueError:
                returned_model = None
                metadata_invalid = True
            try:
                response_id = self._optional_string(getattr(response, "response_id", None))
            except ValueError:
                response_id = None
                metadata_invalid = True
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
                    requested_model=self.model,
                    attempts=tuple(attempts),
                )
            if returned_model is None or response_id is None:
                error = JudgeSafeError(
                    code="invalid_response",
                    message="The judge provider returned incomplete response metadata.",
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
                    requested_model=self.model,
                    attempts=tuple(attempts),
                )
            try:
                verdicts, critique = self._parse_response(request, response)
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
                    requested_model=self.model,
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
                    requested_model=self.model,
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
    def _validate_request(request: JudgeRequest) -> JudgeSafeError | None:
        return validate_judge_bindings(request.bindings)

    def _generate_content_config(self) -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )

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
        response: Any,
    ) -> tuple[tuple[JudgeVerdict, ...], str]:
        raw = getattr(response, "text", None)
        if not isinstance(raw, str) or not raw.strip():
            raise _InvalidJudgeResponseError
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as error:
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
                status
                in {
                    DimensionStatus.INCOMPLETE,
                    DimensionStatus.NOT_APPLICABLE,
                }
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

    @staticmethod
    def _classify_provider_error(error: Exception) -> JudgeSafeError:
        status_code = getattr(error, "code", None)
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            status_code = None
        error_name = type(error).__name__.lower()

        if status_code == 401 or error_name in {
            "unauthenticated",
            "authenticationerror",
        }:
            return JudgeSafeError(
                code="provider_authentication_failed",
                message="The judge provider could not authenticate the request.",
                retryable=False,
            )
        if status_code == 403 or error_name in {"permissiondenied", "forbidden"}:
            return JudgeSafeError(
                code="provider_permission_denied",
                message="The judge provider denied the request.",
                retryable=False,
            )
        if status_code == 429 or error_name in {
            "ratelimiterror",
            "resourceexhausted",
            "toomanyrequests",
        }:
            return JudgeSafeError(
                code="provider_rate_limited",
                message="The judge provider rate limit was reached.",
                retryable=True,
            )
        if status_code in {400, 404, 409, 422} or error_name in {
            "badrequest",
            "invalidargument",
        }:
            return JudgeSafeError(
                code="invalid_request",
                message="The judge provider rejected the request.",
                retryable=False,
            )
        if (
            status_code in {408, 425}
            or (status_code is not None and 500 <= status_code <= 599)
            or isinstance(error, (ConnectionError, TimeoutError))
            or error_name
            in {
                "deadlineexceeded",
                "servererror",
                "serviceunavailable",
            }
        ):
            return JudgeSafeError(
                code="provider_unavailable",
                message="The judge provider could not complete the request.",
                retryable=True,
            )
        return JudgeSafeError(
            code="provider_error",
            message="The judge provider returned an unclassified error.",
            retryable=False,
        )

    @staticmethod
    def _usage(response: Any) -> tuple[TokenUsage, bool]:
        metadata = getattr(response, "usage_metadata", None)
        values: list[int | None] = []
        invalid = False
        for attribute in (
            "prompt_token_count",
            "candidates_token_count",
            "total_token_count",
        ):
            try:
                value = VertexJudgeAdapter._optional_int(getattr(metadata, attribute, None))
            except ValueError:
                value = None
                invalid = True
            values.append(value)
        return TokenUsage(*values), invalid

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Provider token usage must be a non-negative integer.")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Provider identity metadata must be a string.")
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

"""Amazon Bedrock Converse adapter for closed per-element script detection."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

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
from clearcut.detection.domain.candidates import (
    CandidateItem,
    ClearanceCategory,
    UncertaintyLevel,
)
from clearcut.detection.ports.model_runtime import (
    DetectionAttemptMetadata,
    DetectionFailure,
    DetectionResult,
    DetectionSafeError,
    DetectionSuccess,
    DetectionTokenUsage,
    ModelRuntimePort,
)
from clearcut.scripts.domain.elements import ScriptElement

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {category.value for category in ClearanceCategory}
_VALID_UNCERTAINTY = {"low", "medium", "high"}
_SYSTEM_INSTRUCTION = (
    "You are a screenplay pre-clearance detector. Identify only entities present "
    "in the supplied element that may require qualified human clearance review. "
    "Use only these category values: "
    + ", ".join(sorted(_VALID_CATEGORIES))
    + ". Return the exact JSON schema: "
    '{"candidates": [{"category": str, "text": str, "span_start": int, "span_end": int, "rationale": str, "uncertainty": str}]}. '
    "Do not make decisions, create evidence, change policy, provide legal conclusions, or expose hidden reasoning."
)
_EMPTY_USAGE = DetectionTokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


class _InvalidDetectionResponseError(ValueError):
    pass


class BedrockDetectionAdapter(ModelRuntimePort):
    """Amazon Bedrock implementation of ModelRuntimePort using the Converse API."""

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
            BedrockRole.DETECTION
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

    async def detect_element(self, element: ScriptElement) -> DetectionResult:
        started = time.perf_counter()
        messages = [
            {
                "role": "user",
                "content": [{"text": element.text}],
            }
        ]
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
            error = classify_bedrock_error(provider_exception, DetectionSafeError)
            return DetectionFailure(
                error=error,
                attempt=DetectionAttemptMetadata(
                    status="failed",
                    requested_model=self._model,
                    returned_model=None,
                    response_id=None,
                    usage=_EMPTY_USAGE,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        latency_ms = elapsed_ms(started)
        returned_model = extract_returned_model(response)
        response_id = extract_response_id(response)
        usage, usage_invalid = extract_token_usage(response, DetectionTokenUsage)

        metadata_invalid = usage_invalid
        candidates: tuple[CandidateItem, ...] | None = None
        try:
            raw_text = extract_converse_text(response)
            candidates = self._parse_response(element, raw_text)
        except _InvalidDetectionResponseError:
            candidates = None
            logger.warning(
                "Bedrock detection structured response invalid. model=%r response_id=%r",
                returned_model,
                response_id,
            )

        if metadata_invalid or candidates is None:
            error = DetectionSafeError(
                code="invalid_response",
                message="The detection provider returned an invalid structured response.",
                retryable=True,
            )
            return DetectionFailure(
                error=error,
                attempt=DetectionAttemptMetadata(
                    status="invalid_response",
                    requested_model=self._model,
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        metadata = DetectionAttemptMetadata(
            status="succeeded",
            requested_model=self._model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return DetectionSuccess(candidates=candidates, metadata=metadata)

    @staticmethod
    def _parse_response(
        element: ScriptElement,
        raw_text: str,
    ) -> tuple[CandidateItem, ...]:
        try:
            payload = extract_json_payload(raw_text)
        except (ValueError, json.JSONDecodeError, TypeError) as error:
            raise _InvalidDetectionResponseError from error

        if not isinstance(payload, dict) or set(payload) != {"candidates"}:
            raise _InvalidDetectionResponseError
        raw_candidates = payload["candidates"]
        if not isinstance(raw_candidates, list):
            raise _InvalidDetectionResponseError

        candidates: list[CandidateItem] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict) or set(raw_candidate) != {
                "category",
                "text",
                "span_start",
                "span_end",
                "rationale",
                "uncertainty",
            }:
                raise _InvalidDetectionResponseError

            category_value = raw_candidate["category"]
            text = raw_candidate["text"]
            rationale = raw_candidate["rationale"]
            uncertainty = raw_candidate["uncertainty"]
            span_start = raw_candidate["span_start"]
            span_end = raw_candidate["span_end"]

            if (
                not isinstance(category_value, str)
                or category_value not in _VALID_CATEGORIES
                or not isinstance(text, str)
                or not text.strip()
                or not isinstance(rationale, str)
                or not rationale.strip()
                or len(rationale) > 2000
                or not isinstance(uncertainty, str)
                or uncertainty not in _VALID_UNCERTAINTY
                or isinstance(span_start, bool)
                or not isinstance(span_start, int)
                or isinstance(span_end, bool)
                or not isinstance(span_end, int)
                or span_start < 0
                or span_end <= span_start
            ):
                raise _InvalidDetectionResponseError

            # Approximate span correction: check if reported substring matches
            if span_end > len(element.text) or element.text[span_start:span_end] != text:
                found = element.text.find(text)
                if found < 0:
                    raise _InvalidDetectionResponseError
                span_start = found
                span_end = found + len(text)

            candidates.append(
                CandidateItem.create(
                    category=ClearanceCategory(category_value),
                    element_id=element.element_id,
                    span_start=span_start,
                    span_end=span_end,
                    text=text,
                    rationale=rationale,
                    uncertainty=cast(UncertaintyLevel, uncertainty),
                )
            )
        return tuple(candidates)

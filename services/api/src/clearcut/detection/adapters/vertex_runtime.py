"""Vertex Gemini Flash adapter for closed per-element detection."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, cast

from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfiguration,
    resolve_model_role,
)
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

_VALID_CATEGORIES = {category.value for category in ClearanceCategory}
_VALID_UNCERTAINTY = {"low", "medium", "high"}
_SYSTEM_INSTRUCTION = (
    "You are a screenplay pre-clearance detector. Identify only entities present "
    "in the supplied element that may require qualified human clearance review. "
    "Use only these category values: "
    + ", ".join(sorted(_VALID_CATEGORIES))
    + ". Return the exact JSON schema. Do not make decisions, create evidence, "
    "change policy, provide legal conclusions, or expose hidden reasoning."
)
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "candidates": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "category": {
                        "type": "STRING",
                        "enum": sorted(_VALID_CATEGORIES),
                    },
                    "text": {"type": "STRING"},
                    "span_start": {"type": "INTEGER"},
                    "span_end": {"type": "INTEGER"},
                    "rationale": {"type": "STRING", "maxLength": 2000},
                    "uncertainty": {
                        "type": "STRING",
                        "enum": sorted(_VALID_UNCERTAINTY),
                    },
                },
                "required": [
                    "category",
                    "text",
                    "span_start",
                    "span_end",
                    "rationale",
                    "uncertainty",
                ],
            },
        }
    },
    "required": ["candidates"],
}
_EMPTY_USAGE = DetectionTokenUsage(
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
)


class _InvalidDetectionResponseError(ValueError):
    pass


class VertexDetectionRuntime(ModelRuntimePort):
    def __init__(
        self,
        project: str,
        location: str = "global",
        role_configuration: ModelRoleConfiguration | None = None,
        client: Any | None = None,
    ) -> None:
        self.project = project
        self.location = location
        self.role_configuration = role_configuration or resolve_model_role(
            GeminiRole.DETECTION
        )
        if self.role_configuration.role is not GeminiRole.DETECTION:
            raise ValueError("VertexDetectionRuntime requires the detection model role.")
        self.model = self.role_configuration.model
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client

    @property
    def requested_model(self) -> str:
        return self.model

    async def detect_element(self, element: ScriptElement) -> DetectionResult:
        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents=element.text,
                config=self._generate_content_config(),
            )
        except Exception as provider_exception:
            latency_ms = self._elapsed_ms(started)
            error = self._classify_provider_error(provider_exception)
            return DetectionFailure(
                error=error,
                attempt=DetectionAttemptMetadata(
                    status="failed",
                    requested_model=self.model,
                    returned_model=None,
                    response_id=None,
                    usage=_EMPTY_USAGE,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        latency_ms = self._elapsed_ms(started)
        metadata_invalid = False
        try:
            returned_model = self._required_string(
                getattr(response, "model_version", None)
            )
        except _InvalidDetectionResponseError:
            returned_model = None
            metadata_invalid = True
        try:
            response_id = self._required_string(
                getattr(response, "response_id", None)
            )
        except _InvalidDetectionResponseError:
            response_id = None
            metadata_invalid = True
        usage, usage_invalid = self._usage(response)
        metadata_invalid = metadata_invalid or usage_invalid
        try:
            candidates = self._parse_response(element, response)
        except _InvalidDetectionResponseError:
            candidates = None
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
                    requested_model=self.model,
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        metadata = DetectionAttemptMetadata(
            status="succeeded",
            requested_model=self.model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return DetectionSuccess(candidates=candidates, metadata=metadata)

    @staticmethod
    def _generate_content_config() -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )

    @staticmethod
    def _parse_response(
        element: ScriptElement,
        response: Any,
    ) -> tuple[CandidateItem, ...]:
        raw = getattr(response, "text", None)
        if not isinstance(raw, str) or not raw.strip():
            raise _InvalidDetectionResponseError
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as error:
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
                or span_end > len(element.text)
                or element.text[span_start:span_end] != text
            ):
                raise _InvalidDetectionResponseError
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

    @staticmethod
    def _usage(response: Any) -> tuple[DetectionTokenUsage, bool]:
        metadata = getattr(response, "usage_metadata", None)
        values: list[int | None] = []
        invalid = False
        for attribute in (
            "prompt_token_count",
            "candidates_token_count",
            "total_token_count",
        ):
            try:
                value = VertexDetectionRuntime._optional_nonnegative_int(
                    getattr(metadata, attribute, None)
                )
            except _InvalidDetectionResponseError:
                value = None
                invalid = True
            values.append(value)
        return DetectionTokenUsage(*values), invalid

    @staticmethod
    def _optional_nonnegative_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _InvalidDetectionResponseError
        return value

    @staticmethod
    def _required_string(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise _InvalidDetectionResponseError
        return value.strip()

    @staticmethod
    def _classify_provider_error(error: Exception) -> DetectionSafeError:
        status_code = getattr(error, "code", None)
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            status_code = None
        error_name = type(error).__name__.lower()
        if status_code == 401 or error_name in {
            "unauthenticated",
            "authenticationerror",
        }:
            return DetectionSafeError(
                code="provider_authentication_failed",
                message="The detection provider could not authenticate the request.",
                retryable=False,
            )
        if status_code == 403 or error_name in {"permissiondenied", "forbidden"}:
            return DetectionSafeError(
                code="provider_permission_denied",
                message="The detection provider denied the request.",
                retryable=False,
            )
        if status_code == 429 or error_name in {
            "ratelimiterror",
            "resourceexhausted",
            "toomanyrequests",
        }:
            return DetectionSafeError(
                code="provider_rate_limited",
                message="The detection provider rate limit was reached.",
                retryable=True,
            )
        if status_code in {400, 404, 409, 422} or error_name in {
            "badrequest",
            "invalidargument",
        }:
            return DetectionSafeError(
                code="invalid_request",
                message="The detection provider rejected the request.",
                retryable=False,
            )
        if (
            status_code in {408, 425}
            or (status_code is not None and 500 <= status_code <= 599)
            or isinstance(error, (ConnectionError, TimeoutError))
            or error_name in {
                "deadlineexceeded",
                "servererror",
                "serviceunavailable",
            }
        ):
            return DetectionSafeError(
                code="provider_unavailable",
                message="The detection provider could not complete the request.",
                retryable=True,
            )
        return DetectionSafeError(
            code="provider_error",
            message="The detection provider returned an unclassified error.",
            retryable=False,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

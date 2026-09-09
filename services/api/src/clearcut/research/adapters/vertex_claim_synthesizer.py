"""Vertex Gemini adapter for bounded per-snapshot evidence claim synthesis."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from clearcut.ai.model_roles import GeminiRole, ModelRoleConfiguration, resolve_model_role
from clearcut.research.domain.claims import EvidenceStance
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisFailure,
    ClaimSynthesisRequest,
    ClaimSynthesisResult,
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
    SynthesisAttemptMetadata,
    SynthesisSafeError,
    SynthesisTokenUsage,
)

_SYSTEM_INSTRUCTION = (
    "Synthesize one attributable evidence claim for a screenplay pre-clearance "
    "workspace. Use only the supplied source excerpt and clearance item text. "
    "Write exactly one concise sentence, attributable to the source, that states "
    "what the excerpt says about the item. Classify the stance as 'supports', "
    "'disagrees', or 'context'. If the excerpt does not clearly bear on the item, "
    "use stance 'context'. Never invent facts absent from the excerpt, make legal "
    "conclusions, change policy, or expose hidden reasoning."
)
_STANCE_VALUES = [stance.value for stance in EvidenceStance]
_MAX_CLAIM_TEXT_CHARS = 600
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "claim_text": {"type": "STRING", "minLength": 1, "maxLength": _MAX_CLAIM_TEXT_CHARS},
        "stance": {"type": "STRING", "enum": _STANCE_VALUES},
    },
    "required": ["claim_text", "stance"],
}
_EMPTY_USAGE = SynthesisTokenUsage(None, None, None)


class VertexClaimSynthesizer(ClaimSynthesizerPort):
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
            GeminiRole.RESEARCH_PLANNING
        )
        if self.role_configuration.role is not GeminiRole.RESEARCH_PLANNING:
            raise ValueError(
                "VertexClaimSynthesizer requires the research (CLEARCUT_GEMINI_RESEARCH_MODEL) role."
            )
        self.model = self.role_configuration.model
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client

    @property
    def requested_model(self) -> str:
        return self.model

    async def synthesize_claim(
        self,
        request: ClaimSynthesisRequest,
    ) -> ClaimSynthesisResult:
        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents=json.dumps(
                    {
                        "itemId": str(request.item_id),
                        "snapshotId": str(request.snapshot_id),
                        "category": request.category,
                        "itemText": request.item_text,
                        "url": request.url,
                        "publisher": request.publisher,
                        "excerpt": request.excerpt,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                config=self._generate_content_config(),
            )
        except Exception as error:
            safe_error = self._classify_provider_error(error)
            return self._failure(
                safe_error,
                latency_ms=self._elapsed_ms(started),
            )

        latency_ms = self._elapsed_ms(started)
        returned_model = self._optional_string(
            getattr(response, "model_version", None)
        )
        response_id = self._optional_string(getattr(response, "response_id", None))
        usage = self._usage(response)
        try:
            raw = getattr(response, "text", None)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError
            payload = json.loads(raw)
            if not isinstance(payload, dict) or set(payload) != {
                "claim_text",
                "stance",
            }:
                raise ValueError
            claim_text = payload["claim_text"]
            stance_value = payload["stance"]
            if not isinstance(claim_text, str) or not claim_text.strip():
                raise ValueError
            if len(claim_text) > _MAX_CLAIM_TEXT_CHARS:
                raise ValueError
            if not isinstance(stance_value, str):
                raise ValueError
            stance = EvidenceStance(stance_value)
            if returned_model is None or response_id is None or usage is None:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            return self._failure(
                SynthesisSafeError(
                    code="invalid_response",
                    message=(
                        "The claim synthesizer returned an invalid structured response."
                    ),
                    retryable=True,
                ),
                latency_ms=latency_ms,
                returned_model=returned_model,
                response_id=response_id,
                usage=usage or _EMPTY_USAGE,
                status="invalid_response",
            )

        metadata = SynthesisAttemptMetadata(
            status="succeeded",
            requested_model=self.model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return ClaimSynthesisSuccess(
            claim_text=claim_text.strip(),
            stance=stance,
            metadata=metadata,
        )

    @staticmethod
    def _generate_content_config() -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )

    def _failure(
        self,
        error: SynthesisSafeError,
        *,
        latency_ms: int,
        returned_model: str | None = None,
        response_id: str | None = None,
        usage: SynthesisTokenUsage = _EMPTY_USAGE,
        status: str = "failed",
    ) -> ClaimSynthesisFailure:
        return ClaimSynthesisFailure(
            error=error,
            attempt=SynthesisAttemptMetadata(
                status=status,
                requested_model=self.model,
                returned_model=returned_model,
                response_id=response_id,
                usage=usage,
                latency_ms=latency_ms,
                error=error,
            ),
        )

    @staticmethod
    def _usage(response: Any) -> SynthesisTokenUsage | None:
        metadata = getattr(response, "usage_metadata", None)
        values: list[int | None] = []
        for attribute in (
            "prompt_token_count",
            "candidates_token_count",
            "total_token_count",
        ):
            value = getattr(metadata, attribute, None)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                return None
            values.append(value)
        return SynthesisTokenUsage(*values)

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _classify_provider_error(error: Exception) -> SynthesisSafeError:
        status_code = getattr(error, "code", None)
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            status_code = None
        if status_code == 429:
            return SynthesisSafeError(
                code="provider_rate_limited",
                message="The claim synthesizer rate limit was reached.",
                retryable=True,
            )
        if (
            status_code in {408, 425}
            or (status_code is not None and 500 <= status_code <= 599)
            or isinstance(error, (ConnectionError, TimeoutError))
        ):
            return SynthesisSafeError(
                code="provider_unavailable",
                message="The claim synthesizer could not complete the request.",
                retryable=True,
            )
        return SynthesisSafeError(
            code="provider_error",
            message="The claim synthesizer returned an error.",
            retryable=False,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

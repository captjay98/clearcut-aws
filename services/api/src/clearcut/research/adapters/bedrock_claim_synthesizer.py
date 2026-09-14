"""Amazon Bedrock Converse adapter for bounded per-snapshot evidence claim synthesis."""

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

logger = logging.getLogger(__name__)

_MAX_CLAIM_TEXT_CHARS = 600
_SYSTEM_INSTRUCTION = (
    "Synthesize one attributable evidence claim for a screenplay pre-clearance "
    "workspace. Use only the supplied source excerpt and clearance item text. "
    "Write exactly one concise sentence, attributable to the source, that states "
    "what the excerpt says about the item. Classify the stance as 'supports', "
    "'disagrees', or 'context'. Return the exact JSON schema: "
    '{"claim_text": str (1-600 chars), "stance": "supports"|"disagrees"|"context"}. '
    "Never invent facts absent from the excerpt, make legal conclusions, change policy, "
    "or expose hidden reasoning."
)
_EMPTY_USAGE = SynthesisTokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


class BedrockClaimSynthesizer(ClaimSynthesizerPort):
    """Amazon Bedrock implementation of ClaimSynthesizerPort."""

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
            BedrockRole.CLAIM_SYNTHESIS
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

    async def synthesize_claim(
        self,
        request: ClaimSynthesisRequest,
    ) -> ClaimSynthesisResult:
        started = time.perf_counter()
        contents = json.dumps(
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
        )
        messages = [{"role": "user", "content": [{"text": contents}]}]
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
        except Exception as error:
            latency_ms = elapsed_ms(started)
            safe_error = classify_bedrock_error(error, SynthesisSafeError)
            return ClaimSynthesisFailure(
                error=safe_error,
                attempt=SynthesisAttemptMetadata(
                    status="failed",
                    requested_model=self._model,
                    returned_model=None,
                    response_id=None,
                    usage=_EMPTY_USAGE,
                    latency_ms=latency_ms,
                    error=safe_error,
                ),
            )

        latency_ms = elapsed_ms(started)
        returned_model = extract_returned_model(response)
        response_id = extract_response_id(response)
        usage, usage_invalid = extract_token_usage(response, SynthesisTokenUsage)

        claim_text: str | None = None
        stance: EvidenceStance | None = None
        try:
            raw_text = extract_converse_text(response)
            payload = extract_json_payload(raw_text)
            if not isinstance(payload, dict) or set(payload) != {
                "claim_text",
                "stance",
            }:
                raise ValueError("Invalid schema keys for ClaimSynthesis.")
            raw_claim = payload["claim_text"]
            raw_stance = payload["stance"]
            if not isinstance(raw_claim, str) or not raw_claim.strip():
                raise ValueError("claim_text must be non-empty string.")
            if len(raw_claim) > _MAX_CLAIM_TEXT_CHARS:
                raise ValueError("claim_text exceeds maximum characters.")
            if not isinstance(raw_stance, str):
                raise ValueError("stance must be a string.")
            stance = EvidenceStance(raw_stance)
            claim_text = raw_claim.strip()
        except (ValueError, json.JSONDecodeError, TypeError):
            claim_text = None
            stance = None
            logger.warning(
                "Bedrock claim synthesizer structured response invalid. model=%r response_id=%r",
                returned_model,
                response_id,
            )

        if usage_invalid or claim_text is None or stance is None:
            error = SynthesisSafeError(
                code="invalid_response",
                message="The claim synthesizer returned an invalid structured response.",
                retryable=True,
            )
            return ClaimSynthesisFailure(
                error=error,
                attempt=SynthesisAttemptMetadata(
                    status="invalid_response",
                    requested_model=self._model,
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        metadata = SynthesisAttemptMetadata(
            status="succeeded",
            requested_model=self._model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return ClaimSynthesisSuccess(
            claim_text=claim_text,
            stance=stance,
            metadata=metadata,
        )

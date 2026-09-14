"""Amazon Bedrock Converse adapter for bounded research planning."""

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
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.ports.planner import (
    PlanningAttemptMetadata,
    PlanningSafeError,
    PlanningTokenUsage,
    ResearchPlannerPort,
    ResearchPlanningFailure,
    ResearchPlanningRequest,
    ResearchPlanningResult,
    ResearchPlanningSuccess,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "Plan bounded source research for a screenplay pre-clearance workspace. "
    "Return one objective and exactly two or three concise search queries in JSON format: "
    '{"objective": str (20-600 chars), "search_queries": [str (<=200 chars), ...]}. '
    "Use only the supplied item text and category. Do not make legal conclusions, "
    "invent evidence, change policy, or expose hidden reasoning."
)
_EMPTY_USAGE = PlanningTokenUsage(input_tokens=None, output_tokens=None, total_tokens=None)


class BedrockResearchPlanner(ResearchPlannerPort):
    """Amazon Bedrock implementation of ResearchPlannerPort."""

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
            BedrockRole.RESEARCH_PLANNING
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

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult:
        started = time.perf_counter()
        contents = json.dumps(
            {
                "itemId": str(request.item_id),
                "versionId": str(request.version_id),
                "category": request.category,
                "text": request.text,
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
            safe_error = classify_bedrock_error(error, PlanningSafeError)
            return ResearchPlanningFailure(
                error=safe_error,
                attempt=PlanningAttemptMetadata(
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
        usage, usage_invalid = extract_token_usage(response, PlanningTokenUsage)

        plan: ResearchPlan | None = None
        try:
            raw_text = extract_converse_text(response)
            payload = extract_json_payload(raw_text)
            if not isinstance(payload, dict) or set(payload) != {
                "objective",
                "search_queries",
            }:
                raise ValueError("Invalid schema keys for ResearchPlan.")
            plan = ResearchPlan.model_validate(payload)
        except (ValueError, json.JSONDecodeError, TypeError, ValidationError):
            plan = None
            logger.warning(
                "Bedrock research planner structured response invalid. model=%r response_id=%r",
                returned_model,
                response_id,
            )

        if usage_invalid or plan is None:
            error = PlanningSafeError(
                code="invalid_response",
                message="The research planner returned an invalid structured response.",
                retryable=True,
            )
            return ResearchPlanningFailure(
                error=error,
                attempt=PlanningAttemptMetadata(
                    status="invalid_response",
                    requested_model=self._model,
                    returned_model=returned_model,
                    response_id=response_id,
                    usage=usage,
                    latency_ms=latency_ms,
                    error=error,
                ),
            )

        metadata = PlanningAttemptMetadata(
            status="succeeded",
            requested_model=self._model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return ResearchPlanningSuccess(plan=plan, metadata=metadata)

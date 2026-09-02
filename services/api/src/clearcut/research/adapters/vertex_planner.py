"""Vertex Gemini Flash-Lite adapter for bounded research planning."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from clearcut.ai.model_roles import GeminiRole, ModelRoleConfiguration, resolve_model_role
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

_SYSTEM_INSTRUCTION = (
    "Plan bounded source research for a screenplay pre-clearance workspace. "
    "Return one objective and exactly two or three concise search queries. "
    "Use only the supplied item text and category. Do not make legal conclusions, "
    "invent evidence, change policy, or expose hidden reasoning."
)
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "objective": {"type": "STRING", "minLength": 20, "maxLength": 600},
        "search_queries": {
            "type": "ARRAY",
            "minItems": 2,
            "maxItems": 3,
            "items": {"type": "STRING", "maxLength": 200},
        },
    },
    "required": ["objective", "search_queries"],
}
_EMPTY_USAGE = PlanningTokenUsage(None, None, None)


class VertexResearchPlanner(ResearchPlannerPort):
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
                "VertexResearchPlanner requires the research-planning model role."
            )
        self.model = self.role_configuration.model
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client

    @property
    def requested_model(self) -> str:
        return self.model

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult:
        started = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents=json.dumps(
                    {
                        "itemId": str(request.item_id),
                        "versionId": str(request.version_id),
                        "category": request.category,
                        "text": request.text,
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
                "objective",
                "search_queries",
            }:
                raise ValueError
            plan = ResearchPlan.model_validate(payload)
            if returned_model is None or response_id is None or usage is None:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
            return self._failure(
                PlanningSafeError(
                    code="invalid_response",
                    message=(
                        "The research planner returned an invalid structured response."
                    ),
                    retryable=False,
                ),
                latency_ms=latency_ms,
                returned_model=returned_model,
                response_id=response_id,
                usage=usage or _EMPTY_USAGE,
                status="invalid_response",
            )

        metadata = PlanningAttemptMetadata(
            status="succeeded",
            requested_model=self.model,
            returned_model=returned_model,
            response_id=response_id,
            usage=usage,
            latency_ms=latency_ms,
            error=None,
        )
        return ResearchPlanningSuccess(plan=plan, metadata=metadata)

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
        error: PlanningSafeError,
        *,
        latency_ms: int,
        returned_model: str | None = None,
        response_id: str | None = None,
        usage: PlanningTokenUsage = _EMPTY_USAGE,
        status: str = "failed",
    ) -> ResearchPlanningFailure:
        return ResearchPlanningFailure(
            error=error,
            attempt=PlanningAttemptMetadata(
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
    def _usage(response: Any) -> PlanningTokenUsage | None:
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
        return PlanningTokenUsage(*values)

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _classify_provider_error(error: Exception) -> PlanningSafeError:
        status_code = getattr(error, "code", None)
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            status_code = None
        if status_code == 429:
            return PlanningSafeError(
                code="provider_rate_limited",
                message="The research planner rate limit was reached.",
                retryable=True,
            )
        if (
            status_code in {408, 425}
            or (status_code is not None and 500 <= status_code <= 599)
            or isinstance(error, (ConnectionError, TimeoutError))
        ):
            return PlanningSafeError(
                code="provider_unavailable",
                message="The research planner could not complete the request.",
                retryable=True,
            )
        return PlanningSafeError(
            code="provider_error",
            message="The research planner returned an error.",
            retryable=False,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

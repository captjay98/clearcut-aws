"""Typed boundary for bounded research-query planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from clearcut.research.domain.queries import ResearchPlan


@dataclass(frozen=True)
class ResearchPlanningRequest:
    item_id: UUID
    version_id: UUID
    category: str
    text: str
    correlation_id: UUID
    research_run_id: UUID


@dataclass(frozen=True)
class PlanningTokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class PlanningSafeError:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class PlanningAttemptMetadata:
    status: str
    requested_model: str
    returned_model: str | None
    response_id: str | None
    usage: PlanningTokenUsage
    latency_ms: int
    error: PlanningSafeError | None


@dataclass(frozen=True)
class ResearchPlanningSuccess:
    plan: ResearchPlan
    metadata: PlanningAttemptMetadata


@dataclass(frozen=True)
class ResearchPlanningFailure:
    error: PlanningSafeError
    attempt: PlanningAttemptMetadata


ResearchPlanningResult = ResearchPlanningSuccess | ResearchPlanningFailure


class ResearchPlannerPort(Protocol):
    @property
    def requested_model(self) -> str: ...

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult: ...

"""Typed boundary for research workflows (Strands agentic and fallback)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class ResearchWorkflowContext:
    org_id: UUID
    project_id: UUID
    item_id: UUID
    version_id: UUID
    run_id: UUID
    category: str
    item_text: str
    job_id: UUID | None = None
    attempt_number: int = 1
    lease_owner: str = "default-worker"
    correlation_id: UUID | None = None
    policy_version: int = 1
    prompt_version: int = 1


@dataclass(frozen=True)
class ResearchWorkflowResult:
    run_id: UUID
    item_id: UUID
    status: str
    query_count: int
    search_attempt_count: int
    extract_attempt_count: int
    snapshot_count: int
    claim_count: int
    review_status: str
    reason: str
    needs_human_review: bool = True
    cleared: bool = False
    error: str | None = None
    step_count: int = 0
    evaluation_id: UUID | None = None
    headline_score: float | None = None
    judge_passed: bool | None = None
    summary: dict[str, Any] = field(default_factory=dict)


class ResearchWorkflowPort(Protocol):
    async def execute_research(
        self,
        context: ResearchWorkflowContext,
    ) -> ResearchWorkflowResult:
        """Execute bounded research workflow for a clearance item."""
        ...

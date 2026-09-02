"""Persistence port for scoped judge evaluations and safe provider attempts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from clearcut.evaluation.domain.rubric import AgentEvaluation, EvaluationStage
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeBindings,
    JudgeInvocationMetadata,
    JudgeSafeError,
)


class EvaluationPersistenceError(RuntimeError):
    pass


class JudgeInvocationState(StrEnum):
    READY = "ready"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class PreparedJudgeInvocation:
    invocation_id: UUID
    state: JudgeInvocationState
    evaluation: AgentEvaluation | None = None
    error: JudgeSafeError | None = None


class EvaluationRepositoryPort(Protocol):
    async def prepare_invocation(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        stage: EvaluationStage,
        bindings: JudgeBindings,
        requested_model: str,
    ) -> PreparedJudgeInvocation: ...

    async def persist_success(
        self,
        *,
        invocation_id: UUID,
        evaluation: AgentEvaluation,
        critique: str,
        bindings: JudgeBindings,
        metadata: JudgeInvocationMetadata,
    ) -> AgentEvaluation: ...

    async def persist_failure(
        self,
        *,
        invocation_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        bindings: JudgeBindings,
        requested_model: str,
        attempts: tuple[JudgeAttemptMetadata, ...],
    ) -> tuple[UUID, ...]: ...

"""Persistence port for scoped judge evaluations and safe provider attempts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from clearcut.evaluation.domain.gates import GateSeverity
from clearcut.evaluation.domain.rubric import (
    AgentEvaluation,
    EvaluationStage,
    JudgeVerdict,
)
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


@dataclass(frozen=True)
class PersistedGateOutcome:
    """One deterministic gate as it was actually persisted for a run.

    Gate rows are written per detection candidate, so a run holds many rows per
    gate name. The read surface reports one row per gate name and that row is a
    real persisted row rather than a synthesised summary.
    """

    gate_name: str
    passed: bool
    severity: GateSeverity
    details: str


@dataclass(frozen=True)
class PersistedEvaluationProvenance:
    rubric_version: str
    prompt_version: str
    policy_version: str
    requested_model: str
    returned_model: str | None
    input_sha256: str
    latency_ms: int
    total_tokens: int | None
    repair_count: int


@dataclass(frozen=True)
class PersistedEvaluationRecord:
    """A persisted evaluation as the read path is allowed to see it.

    ``agent_evaluations.headline_score`` is deliberately absent. The headline is
    the mean of the scored verdicts and is derived on read, so the read path is
    never handed a second, independently stored number that could drift from the
    dimension rows beneath it.
    """

    evaluation_id: UUID
    org_id: UUID
    project_id: UUID
    run_id: UUID
    stage: EvaluationStage
    blockers_count: int
    critique: str | None
    verdicts: tuple[JudgeVerdict, ...]
    gates: tuple[PersistedGateOutcome, ...]
    provenance: PersistedEvaluationProvenance
    created_at: datetime


class EvaluationLookupState(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class EvaluationLookup:
    """A scoped single-evaluation read outcome.

    Absence is a first-class state rather than a bare ``None`` so callers cannot
    confuse "outside this project scope" with "read failed".
    """

    state: EvaluationLookupState
    record: PersistedEvaluationRecord | None = None

    @classmethod
    def found(cls, record: PersistedEvaluationRecord) -> EvaluationLookup:
        return cls(state=EvaluationLookupState.FOUND, record=record)

    @classmethod
    def not_found(cls) -> EvaluationLookup:
        return cls(state=EvaluationLookupState.NOT_FOUND)


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

    async def list_persisted_evaluations(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[PersistedEvaluationRecord, ...]: ...

    async def get_persisted_evaluation(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        evaluation_id: UUID,
    ) -> EvaluationLookup: ...

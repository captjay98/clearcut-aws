"""Derive the Trust read projection from persisted judge verdicts.

Two invariants live here rather than in the delivery layer, so every caller sees
the same derived numbers:

1. ``headline_score`` is the mean of the dimensions that actually carry a score.
   It is computed from the ``judge_verdicts`` rows on every read and the stored
   ``agent_evaluations.headline_score`` column is never consulted, so the
   headline cannot drift from the rows printed beneath it.
2. A dimension whose status is ``incomplete`` or ``not_applicable`` carries no
   score. It stays ``None`` and is excluded from the mean. A ``failed``
   dimension scores zero by database constraint and is included, because a
   failure is a judged outcome rather than a missing one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from clearcut.evaluation.domain.gates import GateSeverity
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    EvaluationStage,
    JudgeDimension,
    JudgeVerdict,
)
from clearcut.evaluation.ports.repository import (
    EvaluationLookupState,
    EvaluationRepositoryPort,
    PersistedEvaluationRecord,
)

# Statuses whose score participates in the derived headline. ``failed`` is a
# judged zero; ``incomplete`` and ``not_applicable`` are the absence of a score.
_SCORING_STATUSES = frozenset({DimensionStatus.SCORED, DimensionStatus.FAILED})


@dataclass(frozen=True)
class JudgeDimensionScoreView:
    dimension: JudgeDimension
    status: DimensionStatus
    score: float | None
    rationale: str


@dataclass(frozen=True)
class DeterministicGateView:
    gate_name: str
    passed: bool
    severity: GateSeverity
    details: str


@dataclass(frozen=True)
class EvaluationProvenanceView:
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
class TrustEvaluationView:
    evaluation_id: UUID
    org_id: UUID
    project_id: UUID
    run_id: UUID
    stage: EvaluationStage
    headline_score: int | None
    scored_dimensions_count: int
    blockers_count: int
    critique: str | None
    dimensions: tuple[JudgeDimensionScoreView, ...]
    gates: tuple[DeterministicGateView, ...]
    provenance: EvaluationProvenanceView
    created_at: datetime


@dataclass(frozen=True)
class TrustEvaluationNotFound:
    """A scoped absence. The identifier is deliberately not carried."""

    message: str = "Evaluation not found"


TrustEvaluationResult = TrustEvaluationView | TrustEvaluationNotFound


def derive_headline_score(verdicts: tuple[JudgeVerdict, ...]) -> tuple[int | None, int]:
    """Return the derived headline and the count of dimensions behind it.

    The count is the divisor used for the mean, so a reader can always check the
    headline against the rows they were shown. With nothing scored there is no
    honest mean and the headline is ``None`` rather than zero.
    """
    scores = [
        verdict.score
        for verdict in verdicts
        if verdict.status in _SCORING_STATUSES and verdict.score is not None
    ]
    if not scores:
        return None, 0
    # Half-up rounding matches the canonical mock's Math.round; scores are bounded
    # to 0..100 by database constraint so the shift is always on a positive mean.
    return math.floor(sum(scores) / len(scores) + 0.5), len(scores)


def project_evaluation(record: PersistedEvaluationRecord) -> TrustEvaluationView:
    headline_score, scored_dimensions_count = derive_headline_score(record.verdicts)
    return TrustEvaluationView(
        evaluation_id=record.evaluation_id,
        org_id=record.org_id,
        project_id=record.project_id,
        run_id=record.run_id,
        stage=record.stage,
        headline_score=headline_score,
        scored_dimensions_count=scored_dimensions_count,
        blockers_count=record.blockers_count,
        critique=record.critique,
        dimensions=tuple(
            JudgeDimensionScoreView(
                dimension=verdict.dimension,
                status=verdict.status,
                score=verdict.score,
                rationale=verdict.rationale,
            )
            for verdict in record.verdicts
        ),
        gates=tuple(
            DeterministicGateView(
                gate_name=gate.gate_name,
                passed=gate.passed,
                severity=gate.severity,
                details=gate.details,
            )
            for gate in record.gates
        ),
        provenance=EvaluationProvenanceView(
            rubric_version=record.provenance.rubric_version,
            prompt_version=record.provenance.prompt_version,
            policy_version=record.provenance.policy_version,
            requested_model=record.provenance.requested_model,
            returned_model=record.provenance.returned_model,
            input_sha256=record.provenance.input_sha256,
            latency_ms=record.provenance.latency_ms,
            total_tokens=record.provenance.total_tokens,
            repair_count=record.provenance.repair_count,
        ),
        created_at=record.created_at,
    )


class ReadEvaluationsService:
    """Project-scoped Trust reads. Every call carries both scope predicates."""

    def __init__(self, repository: EvaluationRepositoryPort) -> None:
        self._repository = repository

    async def list_evaluations(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[TrustEvaluationView, ...]:
        records = await self._repository.list_persisted_evaluations(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
        )
        return tuple(project_evaluation(record) for record in records)

    async def get_evaluation(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        evaluation_id: UUID,
    ) -> TrustEvaluationResult:
        lookup = await self._repository.get_persisted_evaluation(
            org_id=org_id,
            project_id=project_id,
            evaluation_id=evaluation_id,
        )
        if lookup.state is EvaluationLookupState.NOT_FOUND or lookup.record is None:
            return TrustEvaluationNotFound()
        return project_evaluation(lookup.record)

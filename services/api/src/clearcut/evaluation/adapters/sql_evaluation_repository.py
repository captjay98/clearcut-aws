"""SQL authority for scoped evaluation, verdict, and AI attempt provenance."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import database_wall_clock_sql, session_scope
from clearcut.evaluation.domain.gates import GateSeverity
from clearcut.evaluation.domain.rubric import (
    AgentEvaluation,
    DimensionStatus,
    EvaluationStage,
    JudgeDimension,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeBindings,
    JudgeInvocationMetadata,
    JudgeSafeError,
)
from clearcut.evaluation.ports.repository import (
    EvaluationLookup,
    EvaluationPersistenceError,
    EvaluationRepositoryPort,
    JudgeInvocationState,
    PersistedEvaluationProvenance,
    PersistedEvaluationRecord,
    PersistedGateOutcome,
    PreparedJudgeInvocation,
)
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_GATE_SEVERITY_RANK = {
    GateSeverity.INFO: 0,
    GateSeverity.WARNING: 1,
    GateSeverity.BLOCKER: 2,
}


class SqlEvaluationRepository(EvaluationRepositoryPort):
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
    ) -> PreparedJudgeInvocation:
        self._validate_bindings(bindings)
        if job_attempt_number <= 0 or not requested_model.strip():
            raise EvaluationPersistenceError(
                "A judge invocation requires a positive job attempt and model."
            )
        invocation_id = uuid6.uuid7()
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                job = (
                    await session.execute(
                        sa.text(
                            "SELECT status, attempt_count, lease_owner, "
                            "lease_expires_at > CURRENT_TIMESTAMP AS lease_active "
                            "FROM jobs "
                            "WHERE id = :run_id AND org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        {
                            "run_id": str(run_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                        },
                    )
                ).mappings().first()
                if job is None:
                    raise EvaluationPersistenceError(
                        "The scoped judge job does not exist."
                    )
                if (
                    str(job["status"]) != "running"
                    or int(job["attempt_count"]) != job_attempt_number
                ):
                    raise EvaluationPersistenceError(
                        "The judge invocation does not match the active job attempt."
                    )
                if job["lease_owner"] is None or not bool(job["lease_active"]):
                    raise EvaluationPersistenceError(
                        "The judge invocation does not match an active job lease."
                    )
                lease_owner = str(job["lease_owner"])
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )

                row = (
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO ai_judge_invocations (
                                id, org_id, project_id, run_id, job_attempt_number,
                                lease_owner, stage, status, requested_model, rubric_version,
                                prompt_version, policy_version, input_sha256,
                                evaluation_id, safe_error, created_at, completed_at
                            ) VALUES (
                                :id, :org_id, :project_id, :run_id,
                                :job_attempt_number, :lease_owner, :stage, 'pending',
                                :requested_model, :rubric_version, :prompt_version,
                                :policy_version, :input_sha256, NULL, NULL,
                                :created_at, NULL
                            )
                            ON CONFLICT (
                                org_id, project_id, run_id, job_attempt_number, stage
                            ) DO NOTHING
                            RETURNING *
                            """
                        ),
                        {
                            "id": str(invocation_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "job_attempt_number": job_attempt_number,
                            "lease_owner": lease_owner,
                            "stage": stage.value,
                            "requested_model": requested_model,
                            "rubric_version": bindings.rubric_version,
                            "prompt_version": bindings.prompt_version,
                            "policy_version": bindings.policy_version,
                            "input_sha256": bindings.input_sha256,
                            "created_at": now,
                        },
                    )
                ).mappings().first()
                if row is not None:
                    await self._fence_active_lease(
                        session,
                        org_id=org_id,
                        project_id=project_id,
                        run_id=run_id,
                        job_attempt_number=job_attempt_number,
                        lease_owner=lease_owner,
                    )
                    return PreparedJudgeInvocation(
                        invocation_id=self._uuid(row["id"]),
                        state=JudgeInvocationState.READY,
                    )

                row = (
                    await session.execute(
                        sa.text(
                            "SELECT * FROM ai_judge_invocations "
                            "WHERE org_id = :org_id AND project_id = :project_id "
                            "AND run_id = :run_id "
                            "AND job_attempt_number = :job_attempt_number "
                            "AND stage = :stage"
                        ),
                        {
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "job_attempt_number": job_attempt_number,
                            "stage": stage.value,
                        },
                    )
                ).mappings().one()
                self._validate_invocation_bindings(
                    row,
                    bindings=bindings,
                    requested_model=requested_model,
                )
                state = JudgeInvocationState(str(row["status"]))
                evaluation = None
                error = None
                if state is JudgeInvocationState.SUCCEEDED:
                    if row["evaluation_id"] is None:
                        raise EvaluationPersistenceError(
                            "A succeeded judge invocation has no evaluation."
                        )
                    evaluation = await self._load_evaluation(
                        session,
                        evaluation_id=self._uuid(row["evaluation_id"]),
                        org_id=org_id,
                        project_id=project_id,
                    )
                elif state is JudgeInvocationState.FAILED:
                    error = self._safe_error(row["safe_error"])
                    if error is None:
                        raise EvaluationPersistenceError(
                            "A failed judge invocation has no safe error."
                        )
                return PreparedJudgeInvocation(
                    invocation_id=self._uuid(row["id"]),
                    state=state,
                    evaluation=evaluation,
                    error=error,
                )
        except IntegrityError as error:
            raise EvaluationPersistenceError(
                "Judge invocation intent conflicts with the scoped database state."
            ) from error

    async def persist_success(
        self,
        *,
        invocation_id: UUID,
        evaluation: AgentEvaluation,
        critique: str,
        bindings: JudgeBindings,
        metadata: JudgeInvocationMetadata,
    ) -> AgentEvaluation:
        self._validate_success(evaluation, critique, bindings, metadata)
        try:
            async with session_scope() as session:
                invocation = await self._require_pending_invocation(
                    session,
                    invocation_id=invocation_id,
                    org_id=evaluation.org_id,
                    project_id=evaluation.project_id,
                    run_id=evaluation.run_id,
                    bindings=bindings,
                    requested_model=metadata.requested_model,
                )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO agent_evaluations (
                            id, org_id, project_id, run_id, stage,
                            headline_score, scored_dimensions_count, blockers_count,
                            created_at, critique, rubric_version, prompt_version,
                            policy_version, requested_model, returned_model,
                            input_sha256, response_id, input_tokens, output_tokens,
                            total_tokens, latency_ms, repair_count, attempt_group_id
                        ) VALUES (
                            :id, :org_id, :project_id, :run_id, :stage,
                            :headline_score, :scored_dimensions_count, :blockers_count,
                            :created_at, :critique, :rubric_version, :prompt_version,
                            :policy_version, :requested_model, :returned_model,
                            :input_sha256, :response_id, :input_tokens, :output_tokens,
                            :total_tokens, :latency_ms, :repair_count, :attempt_group_id
                        )
                        """
                    ),
                    {
                        "id": str(evaluation.evaluation_id),
                        "org_id": str(evaluation.org_id),
                        "project_id": str(evaluation.project_id),
                        "run_id": str(evaluation.run_id),
                        "stage": evaluation.stage,
                        "headline_score": evaluation.headline_score,
                        "scored_dimensions_count": evaluation.scored_dimensions_count,
                        "blockers_count": evaluation.blockers_count,
                        "created_at": evaluation.created_at,
                        "critique": critique.strip(),
                        "rubric_version": bindings.rubric_version,
                        "prompt_version": bindings.prompt_version,
                        "policy_version": bindings.policy_version,
                        "requested_model": metadata.requested_model,
                        "returned_model": metadata.returned_model,
                        "input_sha256": bindings.input_sha256,
                        "response_id": metadata.response_id,
                        "input_tokens": metadata.usage.input_tokens,
                        "output_tokens": metadata.usage.output_tokens,
                        "total_tokens": metadata.usage.total_tokens,
                        "latency_ms": metadata.latency_ms,
                        "repair_count": metadata.repair_count,
                        "attempt_group_id": str(invocation_id),
                    },
                )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO judge_verdicts (
                            id, evaluation_id, dimension, status, score,
                            rationale, created_at, org_id, project_id
                        ) VALUES (
                            :id, :evaluation_id, :dimension, :status, :score,
                            :rationale, :created_at, :org_id, :project_id
                        )
                        """
                    ),
                    [
                        {
                            "id": str(verdict.verdict_id),
                            "evaluation_id": str(evaluation.evaluation_id),
                            "dimension": verdict.dimension.value,
                            "status": verdict.status.value,
                            "score": verdict.score,
                            "rationale": verdict.rationale,
                            "created_at": verdict.created_at,
                            "org_id": str(evaluation.org_id),
                            "project_id": str(evaluation.project_id),
                        }
                        for verdict in evaluation.verdicts
                    ],
                )
                await self._insert_attempts(
                    session,
                    org_id=evaluation.org_id,
                    project_id=evaluation.project_id,
                    run_id=evaluation.run_id,
                    evaluation_id=evaluation.evaluation_id,
                    attempt_group_id=invocation_id,
                    bindings=bindings,
                    requested_model=metadata.requested_model,
                    attempts=metadata.attempts,
                )
                completed_at = datetime.now(UTC)
                updated = (
                    await session.execute(
                        sa.text(
                            "UPDATE ai_judge_invocations SET status = 'succeeded', "
                            "evaluation_id = :evaluation_id, completed_at = :completed_at "
                            "WHERE id = :invocation_id AND org_id = :org_id "
                            "AND project_id = :project_id AND status = 'pending' "
                            "RETURNING id"
                        ),
                        {
                            "invocation_id": str(invocation_id),
                            "evaluation_id": str(evaluation.evaluation_id),
                            "org_id": str(evaluation.org_id),
                            "project_id": str(evaluation.project_id),
                            "completed_at": completed_at,
                        },
                    )
                ).first()
                if updated is None:
                    raise EvaluationPersistenceError(
                        "The judge invocation was already finalized."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=evaluation.org_id,
                    project_id=evaluation.project_id,
                    run_id=evaluation.run_id,
                    job_attempt_number=int(invocation["job_attempt_number"]),
                    lease_owner=str(invocation["lease_owner"]),
                )
        except IntegrityError as error:
            raise EvaluationPersistenceError(
                "Evaluation provenance conflicts with the scoped database state."
            ) from error
        return evaluation

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
    ) -> tuple[UUID, ...]:
        self._validate_bindings(bindings)
        if not requested_model.strip() or not attempts or attempts[-1].error is None:
            raise EvaluationPersistenceError(
                "A failed judge invocation requires a model, attempts, and safe error."
            )
        terminal_error = attempts[-1].error
        try:
            async with session_scope() as session:
                invocation = await self._require_pending_invocation(
                    session,
                    invocation_id=invocation_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    bindings=bindings,
                    requested_model=requested_model,
                )
                attempt_ids = await self._insert_attempts(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    evaluation_id=None,
                    attempt_group_id=invocation_id,
                    bindings=bindings,
                    requested_model=requested_model,
                    attempts=attempts,
                )
                completed_at = datetime.now(UTC)
                statement = sa.text(
                    "UPDATE ai_judge_invocations SET status = 'failed', "
                    "safe_error = :safe_error, completed_at = :completed_at "
                    "WHERE id = :invocation_id AND org_id = :org_id "
                    "AND project_id = :project_id AND status = 'pending' RETURNING id"
                ).bindparams(
                    sa.bindparam("safe_error", type_=sa.JSON(none_as_null=True))
                )
                updated = (
                    await session.execute(
                        statement,
                        {
                            "invocation_id": str(invocation_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "safe_error": asdict(terminal_error),
                            "completed_at": completed_at,
                        },
                    )
                ).first()
                if updated is None:
                    raise EvaluationPersistenceError(
                        "The judge invocation was already finalized."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=int(invocation["job_attempt_number"]),
                    lease_owner=str(invocation["lease_owner"]),
                )
                return attempt_ids
        except IntegrityError as error:
            raise EvaluationPersistenceError(
                "Judge attempt provenance conflicts with the scoped database state."
            ) from error

    async def list_persisted_evaluations(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[PersistedEvaluationRecord, ...]:
        """Read every persisted evaluation inside one project scope.

        Both ``org_id`` and ``project_id`` are required predicates: a project
        that is not in the caller's organization simply matches nothing.
        """
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT * FROM agent_evaluations "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND (CAST(:run_id AS uuid) IS NULL OR run_id = CAST(:run_id AS uuid)) "
                        "ORDER BY created_at DESC, id DESC"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id) if run_id is not None else None,
                    },
                )
            ).mappings().all()
            return tuple(
                [
                    await self._read_record(
                        session,
                        row,
                        org_id=org_id,
                        project_id=project_id,
                    )
                    for row in rows
                ]
            )

    async def get_persisted_evaluation(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        evaluation_id: UUID,
    ) -> EvaluationLookup:
        """Read one persisted evaluation inside one project scope.

        An evaluation that belongs to another organization or another project is
        indistinguishable from one that never existed.
        """
        async with session_scope() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT * FROM agent_evaluations WHERE id = :evaluation_id "
                        "AND org_id = :org_id AND project_id = :project_id"
                    ),
                    {
                        "evaluation_id": str(evaluation_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            ).mappings().first()
            if row is None:
                return EvaluationLookup.not_found()
            record = await self._read_record(
                session,
                row,
                org_id=org_id,
                project_id=project_id,
            )
        return EvaluationLookup.found(record)

    async def _read_record(
        self,
        session: AsyncSession,
        row: RowMapping,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> PersistedEvaluationRecord:
        evaluation_id = self._uuid(row["id"])
        run_id = self._uuid(row["run_id"])
        verdicts = await self._read_verdicts(
            session,
            evaluation_id=evaluation_id,
            org_id=org_id,
            project_id=project_id,
        )
        gates = await self._read_gates(
            session,
            run_id=run_id,
            org_id=org_id,
            project_id=project_id,
        )
        critique = str(row["critique"]) if row["critique"] is not None else ""
        return PersistedEvaluationRecord(
            evaluation_id=evaluation_id,
            org_id=self._uuid(row["org_id"]),
            project_id=self._uuid(row["project_id"]),
            run_id=run_id,
            stage=EvaluationStage(str(row["stage"])),
            blockers_count=int(row["blockers_count"]),
            # Legacy rows backfilled an empty critique; an empty string is the
            # absence of a critique, not a critique that says nothing.
            critique=critique.strip() or None,
            verdicts=verdicts,
            gates=gates,
            provenance=PersistedEvaluationProvenance(
                rubric_version=str(row["rubric_version"]),
                prompt_version=str(row["prompt_version"]),
                policy_version=str(row["policy_version"]),
                requested_model=str(row["requested_model"]),
                returned_model=(
                    str(row["returned_model"])
                    if row["returned_model"] is not None
                    else None
                ),
                input_sha256=str(row["input_sha256"]),
                latency_ms=int(row["latency_ms"]),
                total_tokens=(
                    int(row["total_tokens"])
                    if row["total_tokens"] is not None
                    else None
                ),
                repair_count=int(row["repair_count"]),
            ),
            created_at=self._datetime(row["created_at"]),
        )

    async def _read_verdicts(
        self,
        session: AsyncSession,
        *,
        evaluation_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> tuple[JudgeVerdict, ...]:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT * FROM judge_verdicts WHERE evaluation_id = :evaluation_id "
                    "AND org_id = :org_id AND project_id = :project_id "
                    "ORDER BY created_at, id"
                ),
                {
                    "evaluation_id": str(evaluation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().all()
        return tuple(
            JudgeVerdict(
                verdict_id=self._uuid(verdict["id"]),
                dimension=JudgeDimension(str(verdict["dimension"])),
                status=DimensionStatus(str(verdict["status"])),
                # A NULL score stays None all the way to the wire. Coercing it to
                # a number here would turn "we did not judge this" into a zero.
                score=(
                    float(verdict["score"]) if verdict["score"] is not None else None
                ),
                rationale=str(verdict["rationale"]),
                created_at=self._datetime(verdict["created_at"]),
            )
            for verdict in rows
        )

    async def _read_gates(
        self,
        session: AsyncSession,
        *,
        run_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> tuple[PersistedGateOutcome, ...]:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT gate_name, passed, severity, details "
                    "FROM deterministic_gate_results "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id ORDER BY created_at, id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).mappings().all()
        representatives: dict[str, PersistedGateOutcome] = {}
        for gate in rows:
            outcome = PersistedGateOutcome(
                gate_name=str(gate["gate_name"]),
                passed=bool(gate["passed"]),
                severity=GateSeverity(str(gate["severity"])),
                details=str(gate["details"]),
            )
            incumbent = representatives.get(outcome.gate_name)
            if incumbent is None or self._outranks(outcome, incumbent):
                representatives[outcome.gate_name] = outcome
        return tuple(
            representatives[gate_name] for gate_name in sorted(representatives)
        )

    @staticmethod
    def _outranks(
        candidate: PersistedGateOutcome,
        incumbent: PersistedGateOutcome,
    ) -> bool:
        """Decide which real gate row represents a gate name for a whole run.

        A failure always displaces a pass, and a worse failure displaces a milder
        one, so the surfaced row is the most serious thing the gate actually
        recorded. Ties keep the earliest row.
        """
        if incumbent.passed and not candidate.passed:
            return True
        if candidate.passed or incumbent.passed:
            return False
        return _GATE_SEVERITY_RANK[candidate.severity] > _GATE_SEVERITY_RANK[
            incumbent.severity
        ]

    async def _insert_attempts(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        evaluation_id: UUID | None,
        attempt_group_id: UUID,
        bindings: JudgeBindings,
        requested_model: str,
        attempts: tuple[JudgeAttemptMetadata, ...],
    ) -> tuple[UUID, ...]:
        now = datetime.now(UTC)
        attempt_ids = tuple(uuid6.uuid7() for _attempt in attempts)
        statement = sa.text(
            """
            INSERT INTO ai_provider_attempts (
                id, org_id, project_id, run_id, evaluation_id,
                attempt_group_id, ordinal, role, status, requested_model,
                returned_model, rubric_version, prompt_version, policy_version,
                input_sha256, response_id, input_tokens, output_tokens,
                total_tokens, latency_ms, safe_error, created_at, completed_at
            ) VALUES (
                :id, :org_id, :project_id, :run_id, :evaluation_id,
                :attempt_group_id, :ordinal, 'judge', :status, :requested_model,
                :returned_model, :rubric_version, :prompt_version, :policy_version,
                :input_sha256, :response_id, :input_tokens, :output_tokens,
                :total_tokens, :latency_ms, :safe_error, :created_at, :completed_at
            )
            """
        ).bindparams(
            sa.bindparam("safe_error", type_=sa.JSON(none_as_null=True))
        )
        await session.execute(
            statement,
            [
                {
                    "id": str(attempt_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                    "evaluation_id": (
                        str(evaluation_id) if evaluation_id is not None else None
                    ),
                    "attempt_group_id": str(attempt_group_id),
                    "ordinal": attempt.ordinal,
                    "status": attempt.status,
                    "requested_model": requested_model,
                    "returned_model": attempt.returned_model,
                    "rubric_version": bindings.rubric_version,
                    "prompt_version": bindings.prompt_version,
                    "policy_version": bindings.policy_version,
                    "input_sha256": bindings.input_sha256,
                    "response_id": attempt.response_id,
                    "input_tokens": attempt.usage.input_tokens,
                    "output_tokens": attempt.usage.output_tokens,
                    "total_tokens": attempt.usage.total_tokens,
                    "latency_ms": attempt.latency_ms,
                    "safe_error": (
                        asdict(attempt.error) if attempt.error is not None else None
                    ),
                    "created_at": now,
                    "completed_at": now,
                }
                for attempt_id, attempt in zip(attempt_ids, attempts, strict=True)
            ],
        )
        return attempt_ids

    async def _require_pending_invocation(
        self,
        session: AsyncSession,
        *,
        invocation_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        bindings: JudgeBindings,
        requested_model: str,
    ) -> RowMapping:
        row = (
            await session.execute(
                sa.text(
                    "SELECT * FROM ai_judge_invocations "
                    "WHERE id = :invocation_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "invocation_id": str(invocation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().first()
        if row is None or self._uuid(row["run_id"]) != run_id:
            raise EvaluationPersistenceError(
                "The scoped judge invocation does not exist."
            )
        self._validate_invocation_bindings(
            row,
            bindings=bindings,
            requested_model=requested_model,
        )
        if JudgeInvocationState(str(row["status"])) is not JudgeInvocationState.PENDING:
            raise EvaluationPersistenceError(
                "The judge invocation was already finalized."
            )
        job = (
            await session.execute(
                sa.text(
                    "SELECT status, attempt_count, lease_owner, "
                    "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().first()
        if (
            job is None
            or str(job["status"]) != "running"
            or int(job["attempt_count"]) != int(row["job_attempt_number"])
        ):
            raise EvaluationPersistenceError(
                "The judge invocation does not match the active job attempt."
            )
        if (
            job["lease_owner"] is None
            or str(job["lease_owner"]) != str(row["lease_owner"])
            or not bool(job["lease_active"])
        ):
            raise EvaluationPersistenceError(
                "The judge invocation does not match an active job lease."
            )
        await self._fence_active_lease(
            session,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=int(row["job_attempt_number"]),
            lease_owner=str(row["lease_owner"]),
        )
        return row

    async def _fence_active_lease(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
    ) -> None:
        clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
        fenced = (
            await session.execute(
                sa.text(
                    f"UPDATE jobs SET updated_at = {clock_sql} "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id AND status = 'running' "
                    "AND attempt_count = :job_attempt_number "
                    "AND lease_owner = :lease_owner "
                    f"AND lease_expires_at > {clock_sql} RETURNING id"
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "job_attempt_number": job_attempt_number,
                    "lease_owner": lease_owner,
                },
            )
        ).first()
        if fenced is None:
            raise EvaluationPersistenceError(
                "The judge write does not match an active job lease."
            )

    @staticmethod
    def _validate_invocation_bindings(
        row: RowMapping,
        *,
        bindings: JudgeBindings,
        requested_model: str,
    ) -> None:
        expected = (
            bindings.rubric_version,
            bindings.prompt_version,
            bindings.policy_version,
            bindings.input_sha256,
            requested_model,
        )
        persisted = (
            str(row["rubric_version"]),
            str(row["prompt_version"]),
            str(row["policy_version"]),
            str(row["input_sha256"]),
            str(row["requested_model"]),
        )
        if persisted != expected:
            raise EvaluationPersistenceError(
                "A replay cannot change immutable bindings or model identity."
            )

    async def _load_evaluation(
        self,
        session: AsyncSession,
        *,
        evaluation_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> AgentEvaluation:
        row = (
            await session.execute(
                sa.text(
                    "SELECT * FROM agent_evaluations WHERE id = :evaluation_id "
                    "AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "evaluation_id": str(evaluation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().first()
        if row is None:
            raise EvaluationPersistenceError(
                "The terminal judge evaluation was not found in scope."
            )
        verdict_rows = (
            await session.execute(
                sa.text(
                    "SELECT * FROM judge_verdicts WHERE evaluation_id = :evaluation_id "
                    "AND org_id = :org_id AND project_id = :project_id "
                    "ORDER BY created_at, id"
                ),
                {
                    "evaluation_id": str(evaluation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().all()
        verdicts = tuple(
            JudgeVerdict(
                verdict_id=self._uuid(verdict["id"]),
                dimension=JudgeDimension(str(verdict["dimension"])),
                status=DimensionStatus(str(verdict["status"])),
                score=(
                    float(verdict["score"])
                    if verdict["score"] is not None
                    else None
                ),
                rationale=str(verdict["rationale"]),
                created_at=self._datetime(verdict["created_at"]),
            )
            for verdict in verdict_rows
        )
        return AgentEvaluation(
            evaluation_id=self._uuid(row["id"]),
            org_id=self._uuid(row["org_id"]),
            project_id=self._uuid(row["project_id"]),
            run_id=self._uuid(row["run_id"]),
            stage=str(row["stage"]),
            headline_score=(
                float(row["headline_score"])
                if row["headline_score"] is not None
                else None
            ),
            scored_dimensions_count=int(row["scored_dimensions_count"]),
            verdicts=verdicts,
            blockers_count=int(row["blockers_count"]),
            created_at=self._datetime(row["created_at"]),
        )

    @staticmethod
    def _safe_error(value: object) -> JudgeSafeError | None:
        if value is None:
            return None
        try:
            payload = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        code = payload.get("code")
        message = payload.get("message")
        retryable = payload.get("retryable")
        if (
            not isinstance(code, str)
            or not isinstance(message, str)
            or not isinstance(retryable, bool)
        ):
            return None
        return JudgeSafeError(code=code, message=message, retryable=retryable)

    @staticmethod
    def _uuid(value: object) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else result.replace(tzinfo=UTC)

    @classmethod
    def _validate_success(
        cls,
        evaluation: AgentEvaluation,
        critique: str,
        bindings: JudgeBindings,
        metadata: JudgeInvocationMetadata,
    ) -> None:
        cls._validate_bindings(bindings)
        if not critique.strip() or len(critique) > 2000:
            raise EvaluationPersistenceError("Evaluation critique is invalid.")
        dimensions = [verdict.dimension for verdict in evaluation.verdicts]
        if len(dimensions) != len(JudgeDimension) or set(dimensions) != set(
            JudgeDimension
        ):
            raise EvaluationPersistenceError(
                "A persisted evaluation requires exactly one verdict per dimension."
            )
        if (
            not metadata.requested_model.strip()
            or metadata.returned_model is None
            or not metadata.returned_model.strip()
            or metadata.response_id is None
            or not metadata.response_id.strip()
        ):
            raise EvaluationPersistenceError(
                "Successful evaluation provider identity is incomplete."
            )
        if metadata.repair_count not in {0, 1}:
            raise EvaluationPersistenceError("Judge repair count exceeds the bound.")
        if len(metadata.attempts) != metadata.repair_count + 1:
            raise EvaluationPersistenceError(
                "Judge attempt history does not match the repair count."
            )
        if metadata.attempts[-1].status != "succeeded":
            raise EvaluationPersistenceError(
                "Successful evaluation requires a successful terminal attempt."
            )

    @staticmethod
    def _validate_bindings(bindings: JudgeBindings) -> None:
        if any(
            not value.strip()
            for value in (
                bindings.rubric_version,
                bindings.prompt_version,
                bindings.policy_version,
            )
        ):
            raise EvaluationPersistenceError("Evaluation bindings are incomplete.")
        if len(bindings.input_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in bindings.input_sha256.lower()
        ):
            raise EvaluationPersistenceError("Evaluation input hash is invalid.")

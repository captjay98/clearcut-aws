import json
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
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
    TokenUsage,
)
from clearcut.evaluation.ports.repository import (
    EvaluationPersistenceError,
    JudgeInvocationState,
)
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_job() -> tuple[UUID, UUID, UUID]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Judge Owner",
                "email": f"judge-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Judge Studio", "slug": f"judge-{uuid4().hex[:8]}"},
        )
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Judge Project"},
        )
        project_id = UUID(project.json()["data"]["projectId"])

    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="detection",
            idempotency_key=f"judge:{uuid4()}",
            payload={"schemaVersion": 1},
            audit_action="detection.started",
            target_type="project",
            target_id=project_id,
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="judge-repository-test",
    )
    assert claimed is not None
    assert claimed.attempt_count == 1
    return org_id, project_id, claimed.job_id


def _bindings() -> JudgeBindings:
    return JudgeBindings(
        rubric_version="rubric-2026-08-31",
        prompt_version="judge-prompt-v1",
        policy_version="org-policy-v1",
        input_sha256="b" * 64,
    )


async def _prepare(
    repository: SqlEvaluationRepository,
    org_id: UUID,
    project_id: UUID,
    run_id: UUID,
    *,
    job_attempt_number: int = 1,
    bindings: JudgeBindings | None = None,
):
    return await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=job_attempt_number,
        stage=EvaluationStage.DETECTION,
        bindings=bindings or _bindings(),
        requested_model="gemini-3.1-pro-preview",
    )


def _verdicts() -> list[JudgeVerdict]:
    eligible = {
        JudgeDimension.DETECTION_RECALL,
        JudgeDimension.APPROPRIATE_UNCERTAINTY,
        JudgeDimension.LEGAL_BOUNDARY,
        JudgeDimension.TOOL_EFFICIENCY,
    }
    return [
        JudgeVerdict.create(
            dimension=dimension,
            status=(
                DimensionStatus.SCORED
                if dimension in eligible
                else DimensionStatus.NOT_APPLICABLE
            ),
            score=88.0 if dimension in eligible else None,
            rationale=(
                "Bounded score from the supplied evaluation snapshot."
                if dimension in eligible
                else "Not applicable during detection."
            ),
        )
        for dimension in JudgeDimension
    ]


def _metadata() -> JudgeInvocationMetadata:
    invalid_error = JudgeSafeError(
        code="invalid_response",
        message="The judge provider returned an invalid structured response.",
        retryable=False,
    )
    return JudgeInvocationMetadata(
        requested_model="gemini-3.1-pro-preview",
        returned_model="gemini-3.1-pro-preview-20260815",
        response_id="judge-response-2",
        usage=TokenUsage(input_tokens=150, output_tokens=90, total_tokens=240),
        latency_ms=420,
        repair_count=1,
        attempts=(
            JudgeAttemptMetadata(
                ordinal=1,
                status="invalid_response",
                returned_model="gemini-3.1-pro-preview-20260815",
                response_id="judge-response-1",
                usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
                latency_ms=180,
                error=invalid_error,
            ),
            JudgeAttemptMetadata(
                ordinal=2,
                status="succeeded",
                returned_model="gemini-3.1-pro-preview-20260815",
                response_id="judge-response-2",
                usage=TokenUsage(input_tokens=150, output_tokens=90, total_tokens=240),
                latency_ms=240,
                error=None,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_persist_success_binds_evaluation_verdicts_and_each_provider_attempt() -> None:
    org_id, project_id, run_id = await _create_job()
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    repository = SqlEvaluationRepository()
    prepared = await _prepare(repository, org_id, project_id, run_id)
    assert prepared.state is JudgeInvocationState.READY

    persisted = await repository.persist_success(
        invocation_id=prepared.invocation_id,
        evaluation=evaluation,
        critique="Retain explicit uncertainty and qualified human review.",
        bindings=_bindings(),
        metadata=_metadata(),
    )

    assert persisted == evaluation
    replay = await _prepare(repository, org_id, project_id, run_id)
    assert replay.state is JudgeInvocationState.SUCCEEDED
    assert replay.invocation_id == prepared.invocation_id
    assert replay.evaluation == evaluation
    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT * FROM agent_evaluations WHERE id = :evaluation_id "
                    "AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "evaluation_id": str(evaluation.evaluation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().one()
        attempts = (
            await session.execute(
                sa.text(
                    "SELECT * FROM ai_provider_attempts "
                    "WHERE evaluation_id = :evaluation_id ORDER BY ordinal"
                ),
                {"evaluation_id": str(evaluation.evaluation_id)},
            )
        ).mappings().all()
        verdict_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM judge_verdicts "
                    "WHERE evaluation_id = :evaluation_id"
                ),
                {"evaluation_id": str(evaluation.evaluation_id)},
            )
        ).scalar_one()

    assert row["rubric_version"] == "rubric-2026-08-31"
    assert row["prompt_version"] == "judge-prompt-v1"
    assert row["policy_version"] == "org-policy-v1"
    assert row["input_sha256"] == "b" * 64
    assert row["requested_model"] == "gemini-3.1-pro-preview"
    assert row["returned_model"] == "gemini-3.1-pro-preview-20260815"
    assert row["response_id"] == "judge-response-2"
    assert row["input_tokens"] == 150
    assert row["output_tokens"] == 90
    assert row["total_tokens"] == 240
    assert row["latency_ms"] == 420
    assert row["repair_count"] == 1
    assert row["critique"].startswith("Retain explicit uncertainty")
    assert verdict_count == 10
    assert [attempt["status"] for attempt in attempts] == [
        "invalid_response",
        "succeeded",
    ]
    assert all(
        attempt["requested_model"] == "gemini-3.1-pro-preview"
        for attempt in attempts
    )
    assert json.loads(attempts[0]["safe_error"])["code"] == "invalid_response"
    assert attempts[1]["safe_error"] is None


@pytest.mark.asyncio
async def test_persist_failure_records_safe_attempt_without_creating_evaluation() -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    error = JudgeSafeError(
        code="provider_unavailable",
        message="The judge provider could not complete the request.",
        retryable=True,
    )
    attempts = (
        JudgeAttemptMetadata(
            ordinal=1,
            status="failed",
            returned_model=None,
            response_id=None,
            usage=TokenUsage(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
            latency_ms=75,
            error=error,
        ),
    )

    prepared = await _prepare(repository, org_id, project_id, run_id)
    assert prepared.state is JudgeInvocationState.READY
    attempt_ids = await repository.persist_failure(
        invocation_id=prepared.invocation_id,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        bindings=_bindings(),
        requested_model="gemini-3.1-pro-preview",
        attempts=attempts,
    )

    assert len(attempt_ids) == 1
    replay = await _prepare(repository, org_id, project_id, run_id)
    assert replay.state is JudgeInvocationState.FAILED
    assert replay.invocation_id == prepared.invocation_id
    assert replay.error == error
    async with session_scope() as session:
        attempt = (
            await session.execute(
                sa.text(
                    "SELECT * FROM ai_provider_attempts WHERE id = :attempt_id "
                    "AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "attempt_id": str(attempt_ids[0]),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().one()
        evaluation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM agent_evaluations WHERE run_id = :run_id"
                ),
                {"run_id": str(run_id)},
            )
        ).scalar_one()

    assert evaluation_count == 0
    assert attempt["status"] == "failed"
    assert json.loads(attempt["safe_error"]) == {
        "code": "provider_unavailable",
        "message": "The judge provider could not complete the request.",
        "retryable": True,
    }



@pytest.mark.asyncio
async def test_prepare_invocation_blocks_same_attempt_replay_and_allows_later_attempt() -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()

    first = await _prepare(repository, org_id, project_id, run_id)
    same_attempt = await _prepare(repository, org_id, project_id, run_id)

    assert first.state is JudgeInvocationState.READY
    assert same_attempt.state is JudgeInvocationState.PENDING
    assert same_attempt.invocation_id == first.invocation_id

    mismatched_bindings = JudgeBindings(
        rubric_version="rubric-2026-08-31",
        prompt_version="judge-prompt-v1",
        policy_version="org-policy-v1",
        input_sha256="c" * 64,
    )
    with pytest.raises(EvaluationPersistenceError, match="immutable bindings"):
        await _prepare(
            repository,
            org_id,
            project_id,
            run_id,
            bindings=mismatched_bindings,
        )

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET attempt_count = 2 WHERE id = :run_id "
                "AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    later_attempt = await _prepare(
        repository,
        org_id,
        project_id,
        run_id,
        job_attempt_number=2,
    )
    assert later_attempt.state is JudgeInvocationState.READY
    assert later_attempt.invocation_id != first.invocation_id



@pytest.mark.asyncio
async def test_cancelled_job_fences_terminal_evaluation_persistence() -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    prepared = await _prepare(repository, org_id, project_id, run_id)
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET status = 'cancelled', stage = 'cancelled', "
                "lease_owner = NULL, lease_expires_at = NULL "
                "WHERE id = :run_id AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    with pytest.raises(EvaluationPersistenceError, match="active job attempt"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique="Bounded critique.",
            bindings=_bindings(),
            metadata=_metadata(),
        )

    async with session_scope() as session:
        evaluation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM agent_evaluations "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).scalar_one()
    assert evaluation_count == 0




@pytest.mark.asyncio
async def test_expired_lease_fences_terminal_evaluation_persistence() -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    prepared = await _prepare(repository, org_id, project_id, run_id)
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                "WHERE id = :run_id AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    with pytest.raises(EvaluationPersistenceError, match="active job lease"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique="Bounded critique.",
            bindings=_bindings(),
            metadata=_metadata(),
        )


@pytest.mark.asyncio
async def test_lease_loss_after_validation_fences_evaluation_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    prepared = await _prepare(repository, org_id, project_id, run_id)
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    original_execute = AsyncSession.execute
    lease_lost = False

    async def execute_with_lease_loss(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal lease_lost
        result = await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )
        sql = " ".join(str(statement).split())
        if not lease_lost and sql.startswith(
            "SELECT status, attempt_count, lease_owner, "
            "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs"
        ):
            lease_lost = True
            await original_execute(
                session,
                sa.text(
                    "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                params={
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_lease_loss)

    with pytest.raises(EvaluationPersistenceError, match="active job lease"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique="Bounded critique.",
            bindings=_bindings(),
            metadata=_metadata(),
        )

    assert lease_lost is True
    async with session_scope() as session:
        evaluation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM agent_evaluations "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).scalar_one()
    assert evaluation_count == 0


@pytest.mark.asyncio
async def test_lease_loss_after_validation_fences_judge_invocation_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    original_execute = AsyncSession.execute
    lease_lost = False

    async def execute_with_lease_loss(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal lease_lost
        result = await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )
        sql = " ".join(str(statement).split())
        if not lease_lost and sql.startswith(
            "SELECT status, attempt_count, lease_owner, "
            "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs"
        ):
            lease_lost = True
            await original_execute(
                session,
                sa.text(
                    "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                params={
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_lease_loss)

    with pytest.raises(EvaluationPersistenceError, match="active job lease"):
        await _prepare(repository, org_id, project_id, run_id)

    assert lease_lost is True
    async with session_scope() as session:
        invocation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM ai_judge_invocations "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).scalar_one()
    assert invocation_count == 0


@pytest.mark.asyncio
async def test_lease_expiry_after_evaluation_insert_rolls_back_all_judge_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, run_id = await _create_job()
    repository = SqlEvaluationRepository()
    prepared = await _prepare(repository, org_id, project_id, run_id)
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    original_execute = AsyncSession.execute
    lease_expired = False

    async def execute_with_post_insert_expiry(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal lease_expired
        result = await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )
        sql = " ".join(str(statement).split())
        if not lease_expired and sql.startswith("INSERT INTO agent_evaluations"):
            lease_expired = True
            await original_execute(
                session,
                sa.text(
                    "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                params={
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_post_insert_expiry)

    with pytest.raises(EvaluationPersistenceError, match="active job lease"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique="Bounded critique.",
            bindings=_bindings(),
            metadata=_metadata(),
        )

    assert lease_expired is True
    async with session_scope() as session:
        evaluation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM agent_evaluations WHERE id = :evaluation_id"
                ),
                {"evaluation_id": str(evaluation.evaluation_id)},
            )
        ).scalar_one()
        verdict_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM judge_verdicts "
                    "WHERE evaluation_id = :evaluation_id"
                ),
                {"evaluation_id": str(evaluation.evaluation_id)},
            )
        ).scalar_one()
        attempt_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM ai_provider_attempts "
                    "WHERE attempt_group_id = :invocation_id"
                ),
                {"invocation_id": str(prepared.invocation_id)},
            )
        ).scalar_one()
        invocation_status = (
            await session.execute(
                sa.text(
                    "SELECT status FROM ai_judge_invocations "
                    "WHERE id = :invocation_id"
                ),
                {"invocation_id": str(prepared.invocation_id)},
            )
        ).scalar_one()
    assert evaluation_count == 0
    assert verdict_count == 0
    assert attempt_count == 0
    assert invocation_status == "pending"


@pytest.mark.asyncio
async def test_database_rejects_same_tenant_judge_provenance_splicing() -> None:
    org_id, project_id, first_run_id = await _create_job()
    jobs = SqlJobRepository()
    first_job = await jobs.get(
        org_id=org_id,
        project_id=project_id,
        job_id=first_run_id,
    )
    assert first_job is not None
    assert first_job.actor_id is not None
    second = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=first_job.actor_id,
            job_type="detection",
            idempotency_key=f"judge-splice:{uuid4()}",
            payload={"schemaVersion": 1},
            audit_action="detection.started",
            target_type="project",
            target_id=project_id,
        )
    )
    second_job = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=second.job.job_id,
        lease_owner="judge-splice-second",
    )
    assert second_job is not None

    repository = SqlEvaluationRepository()
    first_invocation = await _prepare(
        repository,
        org_id,
        project_id,
        first_run_id,
    )
    second_invocation = await _prepare(
        repository,
        org_id,
        project_id,
        second_job.job_id,
    )
    evaluation = AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=first_run_id,
        stage="detection",
        headline_score=88.0,
        scored_dimensions_count=4,
        verdicts=_verdicts(),
        blockers_count=0,
    )
    await repository.persist_success(
        invocation_id=first_invocation.invocation_id,
        evaluation=evaluation,
        critique="Bounded critique.",
        bindings=_bindings(),
        metadata=_metadata(),
    )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE ai_judge_invocations SET status = 'succeeded', "
                    "evaluation_id = :evaluation_id, completed_at = CURRENT_TIMESTAMP "
                    "WHERE id = :invocation_id"
                ),
                {
                    "evaluation_id": str(evaluation.evaluation_id),
                    "invocation_id": str(second_invocation.invocation_id),
                },
            )

    attempt_values = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "project_id": str(project_id),
        "run_id": str(second_job.job_id),
        "evaluation_id": None,
        "attempt_group_id": str(first_invocation.invocation_id),
        "status": "failed",
    }
    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO ai_provider_attempts "
                    "(id, org_id, project_id, run_id, evaluation_id, "
                    "attempt_group_id, ordinal, role, status, requested_model, "
                    "rubric_version, prompt_version, policy_version, input_sha256, "
                    "latency_ms, created_at, completed_at) VALUES "
                    "(:id, :org_id, :project_id, :run_id, :evaluation_id, "
                    ":attempt_group_id, 99, 'judge', :status, "
                    "'gemini-3.1-pro-preview', 'rubric-2026-08-31', "
                    "'judge-prompt-v1', 'org-policy-v1', :input_sha256, "
                    "1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                attempt_values | {"input_sha256": "b" * 64},
            )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO ai_provider_attempts "
                    "(id, org_id, project_id, run_id, evaluation_id, "
                    "attempt_group_id, ordinal, role, status, requested_model, "
                    "rubric_version, prompt_version, policy_version, input_sha256, "
                    "latency_ms, created_at, completed_at) VALUES "
                    "(:id, :org_id, :project_id, :run_id, :evaluation_id, "
                    ":attempt_group_id, 100, 'judge', 'succeeded', "
                    "'gemini-3.1-pro-preview', 'rubric-2026-08-31', "
                    "'judge-prompt-v1', 'org-policy-v1', :input_sha256, "
                    "1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(second_job.job_id),
                    "evaluation_id": str(evaluation.evaluation_id),
                    "attempt_group_id": str(second_invocation.invocation_id),
                    "input_sha256": "b" * 64,
                },
            )

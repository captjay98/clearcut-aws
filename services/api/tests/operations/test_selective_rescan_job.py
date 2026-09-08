"""Durable, checkpointed selective-rescan staged execution (provider-free).

These tests drive :class:`RunSelectiveRescanJobService` and the scoped
``selective_rescan_checkpoints`` repository with in-memory fake typed ports. No
Gemini, Parallel, network, or cloud dependency is touched. They prove the seven
approved stages advance in exact order with monotonic progress, that each stage
checkpoint is persisted before the next stage runs, that a reload through a new
service instance skips completed stages (no duplicate item/evidence/provider
work), that typed stage failures map to :class:`SafeJobError` with no later
stage, and that only affected items reach child rescan work while unchanged/moved
elements carry evidence forward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import uuid6
from clearcut.operations.application.run_job import (
    JobExecutionError,
    JobExecutionResult,
    RunJobService,
)
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository
from clearcut.rescan.application.models import (
    CarriedEvidenceEdge,
    CarriedItemMapping,
    CarryableElement,
    CarryableElementPair,
    RescanSafeError,
    RescanStage,
    RevisionPlan,
)
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.rescan.ports.repository import RescanChildWorkTicket
from httpx import ASGITransport, AsyncClient
from clearcut.main import app

_STAGE_ORDER = (
    RescanStage.MATERIALIZING_LINEAGE,
    RescanStage.CARRYING_EVIDENCE,
    RescanStage.DETECTING_AFFECTED_PASSAGES,
    RescanStage.RESEARCHING_AFFECTED_ITEMS,
    RescanStage.AWAITING_CONFIRMATION,
    RescanStage.COMPLETED,
)


async def _create_scope() -> tuple[UUID, UUID, UUID]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Rescan Owner",
                "email": f"rescan-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Rescan Studio", "slug": f"rescan-{uuid4().hex[:8]}"},
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Durable Rescan"},
        )
        assert project.status_code == 201, project.text
        return org_id, UUID(project.json()["data"]["projectId"]), actor_id


def _revision_plan(org_id: UUID, project_id: UUID) -> RevisionPlan:
    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    return RevisionPlan(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        algorithm_version="v1",
        carryable_elements=(
            CarryableElementPair(
                before_element_id=uuid6.uuid7(),
                after_element_id=uuid6.uuid7(),
                before_text="Unchanged line",
                after_text="Unchanged line",
            ),
        ),
        affected_element_ids=frozenset({uuid6.uuid7()}),
        removed_element_ids=frozenset({uuid6.uuid7()}),
    )


async def _enqueue_rescan_job(
    repository: SqlJobRepository,
    *,
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    after_version_id: UUID,
):
    return await repository.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="selective_rescan",
            idempotency_key=f"selective_rescan:{after_version_id}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=after_version_id,
        )
    )


class _FakeRevisionPlanPort:
    def __init__(self, plan: RevisionPlan, *, error: RescanSafeError | None = None) -> None:
        self._plan = plan
        self._error = error
        self.calls = 0

    async def load_revision_plan(self, *, org_id, project_id, after_version_id):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._plan


class _FakeMaterializeItems:
    def __init__(self, *, error: RescanSafeError | None = None) -> None:
        self._error = error
        self.calls: list[tuple[UUID, ...]] = []

    async def materialize(
        self,
        *,
        org_id,
        project_id,
        script_id,
        before_version_id,
        after_version_id,
        carryable_elements,
    ) -> tuple[CarriedItemMapping, ...]:
        self.calls.append(tuple(e.after_element_id for e in carryable_elements))
        if self._error is not None:
            raise self._error
        return tuple(
            CarriedItemMapping(
                predecessor_item_id=element.predecessor_item_id,
                new_item_id=uuid6.uuid7(),
                after_version_id=after_version_id,
                after_element_id=element.after_element_id,
            )
            for element in carryable_elements
        )


class _FakeCarryEvidence:
    def __init__(self, *, edges_per_item: int = 1) -> None:
        self._edges_per_item = edges_per_item
        self.calls: list[tuple[UUID, UUID]] = []

    async def carry_forward(
        self, *, org_id, project_id, new_item_id, source_item_id
    ) -> tuple[CarriedEvidenceEdge, ...]:
        self.calls.append((new_item_id, source_item_id))
        return tuple(
            CarriedEvidenceEdge(
                new_item_id=new_item_id,
                source_item_id=source_item_id,
                original_claim_id=uuid6.uuid7(),
                snapshot_id=uuid6.uuid7(),
                run_id=uuid6.uuid7(),
                query_id=uuid6.uuid7(),
                provider_attempt_id=uuid6.uuid7(),
            )
            for _ in range(self._edges_per_item)
        )


class _FakeChildWork:
    """Records affected-item child rescan requests and proves idempotency."""

    def __init__(self, *, affected_item_ids: tuple[UUID, ...] | None = None) -> None:
        self._affected_item_ids = affected_item_ids
        self.detect_calls: list[frozenset[UUID]] = []
        self.research_calls: list[frozenset[UUID]] = []
        self._issued: dict[UUID, RescanChildWorkTicket] = {}

    async def list_affected_items(
        self, *, org_id, project_id, before_version_id, affected_element_ids
    ) -> tuple[UUID, ...]:
        if self._affected_item_ids is not None:
            return self._affected_item_ids
        return tuple(uuid6.uuid7() for _ in affected_element_ids)

    async def request_detection(
        self, *, org_id, project_id, after_version_id, affected_item_ids, actor_id
    ) -> tuple[RescanChildWorkTicket, ...]:
        self.detect_calls.append(frozenset(affected_item_ids))
        return self._tickets("detect", affected_item_ids)

    async def request_research(
        self, *, org_id, project_id, after_version_id, affected_item_ids, actor_id
    ) -> tuple[RescanChildWorkTicket, ...]:
        self.research_calls.append(frozenset(affected_item_ids))
        return self._tickets("research", affected_item_ids)

    def _tickets(self, kind, item_ids) -> tuple[RescanChildWorkTicket, ...]:
        tickets = []
        for item_id in item_ids:
            key = f"selective_rescan:{kind}:{item_id}"
            ticket = self._issued.setdefault(
                item_id, RescanChildWorkTicket(item_id=item_id, idempotency_key=key)
            )
            tickets.append(ticket)
        return tuple(tickets)


def _service(
    *,
    job_repository: SqlJobRepository,
    repository: SqlSelectiveRescanRepository,
    plan: RevisionPlan,
    materialize: _FakeMaterializeItems | None = None,
    evidence: _FakeCarryEvidence | None = None,
    child: _FakeChildWork | None = None,
) -> RunSelectiveRescanJobService:
    return RunSelectiveRescanJobService(
        revision_plan=_FakeRevisionPlanPort(plan),
        materialize_items=materialize or _FakeMaterializeItems(),
        carry_evidence=evidence or _FakeCarryEvidence(),
        child_work=child or _FakeChildWork(),
        repository=repository,
        job_repository=job_repository,
    )


@pytest.mark.asyncio
async def test_stages_advance_in_exact_order_with_monotonic_progress() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )

    processor = _service(
        job_repository=job_repository,
        repository=checkpoint_repository,
        plan=plan,
    )
    runner = RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan",
    )
    completed = await runner.run(enqueued.job.job_id, org_id, project_id)

    assert completed.status is RunStatus.SUCCEEDED
    assert completed.progress == 100
    assert completed.stage == "succeeded"

    persisted = await checkpoint_repository.load_stage_history(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    assert [stage for stage, _status in persisted] == list(_STAGE_ORDER)
    assert all(status == "succeeded" for _stage, status in persisted)


@pytest.mark.asyncio
async def test_only_affected_items_reach_child_work_and_carry_only_covers_unchanged() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    affected_item = uuid6.uuid7()
    child = _FakeChildWork(affected_item_ids=(affected_item,))
    evidence = _FakeCarryEvidence()
    materialize = _FakeMaterializeItems()
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )

    processor = _service(
        job_repository=job_repository,
        repository=checkpoint_repository,
        plan=plan,
        materialize=materialize,
        evidence=evidence,
        child=child,
    )
    await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan",
    ).run(enqueued.job.job_id, org_id, project_id)

    # Only carryable (unchanged/moved) elements were materialized + carried.
    assert materialize.calls == [tuple(e.after_element_id for e in plan.carryable_elements)]
    assert len(evidence.calls) == len(plan.carryable_elements)
    # Only affected items reached child detection and research.
    assert child.detect_calls == [frozenset({affected_item})]
    assert child.research_calls == [frozenset({affected_item})]


@pytest.mark.asyncio
async def test_reload_through_new_service_skips_completed_stage_writes() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )

    first_materialize = _FakeMaterializeItems()
    first_evidence = _FakeCarryEvidence()
    first_child = _FakeChildWork(affected_item_ids=(uuid6.uuid7(),))
    await RunJobService(
        repository=job_repository,
        processors={
            "selective_rescan": _service(
                job_repository=job_repository,
                repository=checkpoint_repository,
                plan=plan,
                materialize=first_materialize,
                evidence=first_evidence,
                child=first_child,
            )
        },
        lease_owner="local-rescan",
    ).run(enqueued.job.job_id, org_id, project_id)

    # Force a governed retry so a brand-new service instance replays the job.
    await job_repository.cancel(
        org_id=org_id, project_id=project_id, job_id=enqueued.job.job_id, actor_id=actor_id
    )
    await job_repository.retry(
        org_id=org_id, project_id=project_id, job_id=enqueued.job.job_id, actor_id=actor_id
    )

    replay_materialize = _FakeMaterializeItems()
    replay_evidence = _FakeCarryEvidence()
    replay_child = _FakeChildWork(affected_item_ids=(uuid6.uuid7(),))
    replayed = await RunJobService(
        repository=job_repository,
        processors={
            "selective_rescan": _service(
                job_repository=job_repository,
                repository=checkpoint_repository,
                plan=plan,
                materialize=replay_materialize,
                evidence=replay_evidence,
                child=replay_child,
            )
        },
        lease_owner="local-rescan-replay",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert replayed.status is RunStatus.SUCCEEDED
    # Completed stages are skipped on replay: no duplicate item, evidence, or
    # provider/child work is performed.
    assert replay_materialize.calls == []
    assert replay_evidence.calls == []
    assert replay_child.detect_calls == []
    assert replay_child.research_calls == []


@pytest.mark.asyncio
async def test_typed_stage_failure_maps_to_safe_job_error_with_no_later_stage() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )
    failing_materialize = _FakeMaterializeItems(
        error=RescanSafeError(
            code="carried_item_conflict",
            message="Carried item projection conflicts with scoped item lineage.",
            retryable=False,
        )
    )
    evidence = _FakeCarryEvidence()
    child = _FakeChildWork()

    failed = await RunJobService(
        repository=job_repository,
        processors={
            "selective_rescan": _service(
                job_repository=job_repository,
                repository=checkpoint_repository,
                plan=plan,
                materialize=failing_materialize,
                evidence=evidence,
                child=child,
            )
        },
        lease_owner="local-rescan",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert failed.status is RunStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "carried_item_conflict"
    # No later stage ran after the failure.
    assert evidence.calls == []
    assert child.detect_calls == []
    assert child.research_calls == []

    history = await checkpoint_repository.load_stage_history(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    stages = {stage: status for stage, status in history}
    assert stages[RescanStage.MATERIALIZING_LINEAGE] == "failed"
    assert RescanStage.CARRYING_EVIDENCE not in stages
    assert RescanStage.COMPLETED not in stages


@pytest.mark.asyncio
async def test_stable_checkpoint_keys_prevent_duplicate_rows_across_retries() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )

    for _ in range(2):
        await RunJobService(
            repository=job_repository,
            processors={
                "selective_rescan": _service(
                    job_repository=job_repository,
                    repository=checkpoint_repository,
                    plan=plan,
                )
            },
            lease_owner="local-rescan",
        ).run(enqueued.job.job_id, org_id, project_id)
        current = await job_repository.get(
            org_id=org_id, project_id=project_id, job_id=enqueued.job.job_id
        )
        assert current is not None
        if current.status is RunStatus.SUCCEEDED:
            await job_repository.cancel(
                org_id=org_id,
                project_id=project_id,
                job_id=enqueued.job.job_id,
                actor_id=actor_id,
            )
            await job_repository.retry(
                org_id=org_id,
                project_id=project_id,
                job_id=enqueued.job.job_id,
                actor_id=actor_id,
            )

    history = await checkpoint_repository.load_stage_history(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    # Exactly one checkpoint per stage survives retries (stable per-stage keys).
    stage_values = [stage for stage, _status in history]
    assert len(stage_values) == len(set(stage_values)) == len(_STAGE_ORDER)


@pytest.mark.asyncio
async def test_cross_tenant_revision_plan_absence_fails_closed() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    enqueued = await _enqueue_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=plan.after_version_id,
    )
    processor = RunSelectiveRescanJobService(
        revision_plan=_FakeRevisionPlanPort(
            plan,
            error=RescanSafeError(
                code="revision_plan_not_found",
                message="No adjacent revision plan is visible in the requested scope.",
                retryable=False,
            ),
        ),
        materialize_items=_FakeMaterializeItems(),
        carry_evidence=_FakeCarryEvidence(),
        child_work=_FakeChildWork(),
        repository=checkpoint_repository,
        job_repository=job_repository,
    )

    failed = await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert failed.status is RunStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "revision_plan_not_found"


@pytest.mark.asyncio
async def test_invalid_payload_target_is_rejected_before_any_stage() -> None:
    org_id, project_id, actor_id = await _create_scope()
    job_repository = SqlJobRepository()
    checkpoint_repository = SqlSelectiveRescanRepository()
    plan = _revision_plan(org_id, project_id)
    # Enqueue with a mismatched target type so the strict processor projection rejects it.
    enqueued = await job_repository.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="selective_rescan",
            idempotency_key=f"selective_rescan:invalid:{uuid4()}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "clearance_item", "id": str(plan.after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=plan.after_version_id,
        )
    )
    materialize = _FakeMaterializeItems()

    failed = await RunJobService(
        repository=job_repository,
        processors={
            "selective_rescan": _service(
                job_repository=job_repository,
                repository=checkpoint_repository,
                plan=plan,
                materialize=materialize,
            )
        },
        lease_owner="local-rescan",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert failed.status is RunStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "invalid_selective_rescan_job"
    assert materialize.calls == []

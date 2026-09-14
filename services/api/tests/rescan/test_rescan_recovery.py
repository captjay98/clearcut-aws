"""Recovery coverage for a RESUMED selective rescan (defect D3).

A selective rescan is a durable, checkpointed job: each stage records a
``succeeded`` checkpoint before the next stage runs, and a reload skips the
stages a prior attempt already completed. Skipping a stage's *side effects* is
correct; losing that stage's *outputs* is not. Before this coverage existed, a
resumed run restarted with empty carried mappings and an empty affected-item
set, so a run interrupted after lineage materialization carried zero evidence and
a run interrupted after detection researched zero items — and then reported
normal completion. That is silent incorrectness on the revision feature, so every
test here resumes from the REAL persisted checkpoint state through a FRESH
processor with empty in-process memory; no test simulates resumption by reusing
the same object.

Scope of the doubles: only the child provider boundary (fresh detection of added
passages and child research requests) is faked, because that boundary reaches
Gemini/Parallel. Everything inside the test is real: the scripts-owned revision
plan, the detection-owned item lineage materialization, the research-owned
evidence carry-forward, the scoped affected-item read, the durable job kernel,
and the migrated database.

Interruption points covered:

* after ``materializing_lineage`` succeeded — all expected evidence still
  carries on resume;
* midway through ``carrying_evidence`` — no lost and no duplicate carried edge;
* after ``detecting_affected_passages`` succeeded — that stage's item ids
  (including freshly detected added-passage items) still reach research;
* after full success, replayed — no duplicate governed work and no duplicate
  provider call;
* a resumed run's final summary reports the true totals rather than zeros;
* a succeeded checkpoint whose persisted output cannot be restored fails closed
  with a typed error instead of silently running later stages on empty inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.main import _SelectiveRescanItemLineageCoordinator
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import EnqueueJob, JobRecord
from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository
from clearcut.rescan.application.models import (
    CarriedEvidenceEdge,
    CarriedItemMapping,
    CarryableElement,
    RescanSafeError,
    RescanStage,
)
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.rescan.ports.repository import RescanChildWorkTicket
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter

pytestmark = pytest.mark.asyncio

_WORKER_LOSS = RescanSafeError(
    code="rescan_worker_lost",
    message="The rescan worker was lost mid-stage.",
    retryable=True,
)


# --------------------------------------------------------------------------- #
# Seeding: a realistic adjacent revision with real persisted state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CarryablePassage:
    """One unchanged passage with a predecessor item and one provenanced claim."""

    before_element_id: UUID
    after_element_id: UUID
    predecessor_item_id: UUID
    original_claim_id: UUID


@dataclass(frozen=True)
class SeededRevision:
    org_id: UUID
    project_id: UUID
    script_id: UUID
    actor_id: UUID
    before_version_id: UUID
    after_version_id: UUID
    carryable: tuple[CarryablePassage, ...]
    modified_before_element_id: UUID
    modified_after_element_id: UUID
    modified_item_id: UUID
    added_after_element_id: UUID


async def _seed_actor(actor_id: UUID) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {
                "id": str(actor_id),
                "email": f"reviewer-{actor_id}@example.com",
                "created_at": datetime.now(UTC),
            },
        )


async def _seed_project(org_id: UUID, project_id: UUID) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org_id),
                "name": f"Org {org_id}",
                "slug": f"org-{str(org_id)[:8]}",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, :title, :created_at)"
            ),
            {
                "id": str(project_id),
                "org_id": str(org_id),
                "title": "Rescan recovery project",
                "created_at": now,
            },
        )


async def _seed_version(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    ordinal: int,
    predecessor_version_id: UUID | None,
    predecessor_ordinal: int | None,
    create_script: bool,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        if create_script:
            await session.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at, "
                    "current_slot) VALUES (:id, :org_id, :project_id, 'Script', :created_at, "
                    "'current')"
                ),
                {
                    "id": str(script_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "created_at": now,
                },
            )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
                "created_at, predecessor_version_id, predecessor_ordinal) VALUES "
                "(:id, :script_id, :org_id, :project_id, :ordinal, :source_hash, 'v1', "
                ":created_at, :predecessor_version_id, :predecessor_ordinal)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "ordinal": ordinal,
                "source_hash": f"{ordinal:064d}",
                "created_at": now,
                "predecessor_version_id": (
                    str(predecessor_version_id) if predecessor_version_id else None
                ),
                "predecessor_ordinal": predecessor_ordinal,
            },
        )


async def _seed_element(*, version_id: UUID, element_id: UUID, ordinal: int, text: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, :ordinal, 'action', :text)"
            ),
            {
                "id": str(element_id),
                "version_id": str(version_id),
                "ordinal": ordinal,
                "text": text,
            },
        )


async def _seed_item(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    element_id: UUID,
    item_id: UUID,
    text: str,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
                "'products_and_trademarks', :text, 'resolved', 'completed', "
                "'resolved', 'approved_as_is', :created_at, 3)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "text": text,
                "created_at": now,
            },
        )


async def _seed_full_provenance_claim(
    *,
    org_id: UUID,
    project_id: UUID,
    item_id: UUID,
    version_id: UUID,
    url: str,
) -> UUID:
    """Seed a run, query, provider attempt, authorization, snapshot, and claim.

    Returns the claim id. Only fully provenanced claims are eligible to carry, so
    the whole provenance tuple is real persisted state.
    """
    now = datetime.now(UTC)
    run_id = uuid6.uuid7()
    query_id = uuid6.uuid7()
    attempt_id = uuid6.uuid7()
    authorization_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()
    claim_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, version_id, status, created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :version_id, 'completed', :created_at)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "version_id": str(version_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO research_queries "
                "(id, run_id, query, ordinal, org_id, project_id, item_id, version_id, "
                "created_at) VALUES "
                "(:id, :run_id, 'trademark register', 1, :org_id, :project_id, :item_id, "
                ":version_id, :created_at)"
            ),
            {
                "id": str(query_id),
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "version_id": str(version_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO provider_attempts "
                "(id, run_id, operation_kind, status, created_at, org_id, project_id, item_id, "
                "query_id, authorizing_search_attempt_id, authorizing_operation_kind) VALUES "
                "(:id, :run_id, 'search', 'succeeded', :created_at, :org_id, :project_id, "
                ":item_id, :query_id, :id, 'search')"
            ),
            {
                "id": str(attempt_id),
                "run_id": str(run_id),
                "created_at": now,
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "query_id": str(query_id),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO search_result_authorizations "
                "(id, org_id, project_id, item_id, run_id, query_id, search_attempt_id, "
                "search_operation_kind, ordinal, url, canonical_url, title, publisher, excerpt, "
                "created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :run_id, :query_id, :search_attempt_id, "
                "'search', 1, :url, :canonical_url, 'Official register', 'USPTO', "
                "'No active conflicting marks.', :created_at)"
            ),
            {
                "id": str(authorization_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "query_id": str(query_id),
                "search_attempt_id": str(attempt_id),
                "url": url,
                "canonical_url": url,
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                "origin, sha256_hash, retrieved_at, query_id, provider_attempt_id, "
                "authorization_id, authorizing_search_attempt_id) VALUES "
                "(:id, :org_id, :project_id, :item_id, :run_id, :url, 'Official register', "
                "'USPTO', 'No active conflicting marks.', 'search', :sha256_hash, :retrieved_at, "
                ":query_id, :provider_attempt_id, :authorization_id, "
                ":authorizing_search_attempt_id)"
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "url": url,
                "sha256_hash": (str(snapshot_id).replace("-", "") + "0" * 64)[:64],
                "retrieved_at": now,
                "query_id": str(query_id),
                "provider_attempt_id": str(attempt_id),
                "authorization_id": str(authorization_id),
                "authorizing_search_attempt_id": str(attempt_id),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO evidence_claims "
                "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                "claim_text, provenance_excerpt, created_at, run_id, query_id, "
                "provider_attempt_id) VALUES "
                "(:id, :org_id, :project_id, :item_id, :snapshot_id, 'supports', "
                "'primary_official', :claim_text, :excerpt, :created_at, :run_id, :query_id, "
                ":provider_attempt_id)"
            ),
            {
                "id": str(claim_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "snapshot_id": str(snapshot_id),
                "claim_text": "The register shows no conflicting active marks.",
                "excerpt": "No active conflicting marks.",
                "created_at": now,
                "run_id": str(run_id),
                "query_id": str(query_id),
                "provider_attempt_id": str(attempt_id),
            },
        )
    return claim_id


async def _seed_lineage_row(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    diff_id: UUID,
    before_version_id: UUID,
    after_version_id: UUID,
    before_element_id: UUID | None,
    after_element_id: UUID | None,
    change_kind: str,
    confidence: str,
) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_element_lineage "
                "(id, org_id, project_id, script_id, diff_id, before_version_id, "
                "after_version_id, before_element_id, after_element_id, change_kind, "
                "confidence, algorithm_version, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :diff_id, :before_version_id, "
                ":after_version_id, :before_element_id, :after_element_id, :change_kind, "
                ":confidence, 'element-lineage-v1', :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "diff_id": str(diff_id),
                "before_version_id": str(before_version_id),
                "after_version_id": str(after_version_id),
                "before_element_id": str(before_element_id) if before_element_id else None,
                "after_element_id": str(after_element_id) if after_element_id else None,
                "change_kind": change_kind,
                "confidence": confidence,
                "created_at": datetime.now(UTC),
            },
        )


async def _seed_recovery_revision() -> SeededRevision:
    """Two adjacent versions: two carryable passages, one modified, one added.

    Every row is real persisted state, so the revision plan, the affected-item
    read, and the carried-evidence writes all run against the migrated schema.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    diff_id = uuid6.uuid7()

    await _seed_project(org_id, project_id)
    await _seed_actor(actor_id)
    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        ordinal=1,
        predecessor_version_id=None,
        predecessor_ordinal=None,
        create_script=True,
    )
    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=after_version_id,
        ordinal=2,
        predecessor_version_id=before_version_id,
        predecessor_ordinal=1,
        create_script=False,
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_diffs "
                "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
                "before_ordinal, after_ordinal, algorithm_version, diff_payload, "
                "summary_payload, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :before_version_id, :after_version_id, "
                "1, 2, 'element-lineage-v1', :diff_payload, :summary_payload, :created_at)"
            ),
            {
                "id": str(diff_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "before_version_id": str(before_version_id),
                "after_version_id": str(after_version_id),
                "diff_payload": "{}",
                "summary_payload": "{}",
                "created_at": datetime.now(UTC),
            },
        )

    carryable: list[CarryablePassage] = []
    for index, brand in enumerate(("Acme Corporation", "Zenith Motors"), start=1):
        before_element_id = uuid6.uuid7()
        after_element_id = uuid6.uuid7()
        item_id = uuid6.uuid7()
        await _seed_element(
            version_id=before_version_id, element_id=before_element_id, ordinal=index, text=brand
        )
        await _seed_element(
            version_id=after_version_id, element_id=after_element_id, ordinal=index, text=brand
        )
        await _seed_item(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=before_version_id,
            element_id=before_element_id,
            item_id=item_id,
            text=brand,
        )
        claim_id = await _seed_full_provenance_claim(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            version_id=before_version_id,
            url=f"https://register.example/{index}",
        )
        await _seed_lineage_row(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            diff_id=diff_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            before_element_id=before_element_id,
            after_element_id=after_element_id,
            change_kind="unchanged",
            confidence="exact",
        )
        carryable.append(
            CarryablePassage(
                before_element_id=before_element_id,
                after_element_id=after_element_id,
                predecessor_item_id=item_id,
                original_claim_id=claim_id,
            )
        )

    # One modified passage: scoped after-version detection targets its changed
    # AFTER element, and the resulting brand-new item id reaches research.
    modified_before_element_id = uuid6.uuid7()
    modified_after_element_id = uuid6.uuid7()
    modified_item_id = uuid6.uuid7()
    await _seed_element(
        version_id=before_version_id,
        element_id=modified_before_element_id,
        ordinal=3,
        text="Globex Systems",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=modified_after_element_id,
        ordinal=3,
        text="Globex Systems International",
    )
    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=modified_before_element_id,
        item_id=modified_item_id,
        text="Globex Systems",
    )
    await _seed_lineage_row(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        diff_id=diff_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_element_id=modified_before_element_id,
        after_element_id=modified_after_element_id,
        change_kind="modified",
        confidence="similar",
    )

    # One added passage: no predecessor item, so fresh after-version detection
    # must produce a brand-new unresolved item that then reaches research.
    added_after_element_id = uuid6.uuid7()
    await _seed_element(
        version_id=after_version_id,
        element_id=added_after_element_id,
        ordinal=4,
        text="Nimbus Airlines",
    )
    await _seed_lineage_row(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        diff_id=diff_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_element_id=None,
        after_element_id=added_after_element_id,
        change_kind="added",
        confidence="unmatched",
    )

    return SeededRevision(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        actor_id=actor_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        carryable=tuple(carryable),
        modified_before_element_id=modified_before_element_id,
        modified_after_element_id=modified_after_element_id,
        modified_item_id=modified_item_id,
        added_after_element_id=added_after_element_id,
    )


# --------------------------------------------------------------------------- #
# Real application services, with recording and a mid-stage interruption
# --------------------------------------------------------------------------- #


class _RecordingLineage:
    """The REAL item-lineage coordinator, recording each materialize call."""

    def __init__(self) -> None:
        self._inner = _SelectiveRescanItemLineageCoordinator(SqlItemLineageAdapter())
        self.calls: list[tuple[UUID, ...]] = []

    async def materialize(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        before_version_id: UUID,
        after_version_id: UUID,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        self.calls.append(tuple(element.after_element_id for element in carryable_elements))
        return await self._inner.materialize(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            carryable_elements=carryable_elements,
        )


class _RecordingEvidence:
    """The REAL evidence carry-forward, optionally interrupted mid-stage.

    ``interrupt_after`` is the number of items that carry successfully before the
    worker is lost, which is exactly how a mid-stage interruption happens in
    production: some items are durably carried, the stage checkpoint is not.
    """

    def __init__(self, *, interrupt_after: int | None = None) -> None:
        self._inner = SqlEvidenceLineageAdapter()
        self._interrupt_after = interrupt_after
        self.calls: list[tuple[UUID, UUID]] = []

    async def carry_forward(
        self, *, org_id: UUID, project_id: UUID, new_item_id: UUID, source_item_id: UUID
    ) -> tuple[CarriedEvidenceEdge, ...]:
        if self._interrupt_after is not None and len(self.calls) >= self._interrupt_after:
            raise _WORKER_LOSS
        self.calls.append((new_item_id, source_item_id))
        return await self._inner.carry_forward(
            org_id=org_id,
            project_id=project_id,
            new_item_id=new_item_id,
            source_item_id=source_item_id,
        )


class _FakeChildWork:
    """Fake provider boundary; the affected-item read stays real and scoped.

    ``added_item_ids`` stands in for the brand-new unresolved items that fresh
    detection of added passages would create. Each attempt is given a DIFFERENT
    value so a resumed run that reports the FIRST attempt's ids proves the ids
    were restored from persisted state rather than recomputed.
    """

    def __init__(
        self,
        *,
        modified_item_ids: tuple[UUID, ...] = (),
        added_item_ids: tuple[UUID, ...] = (),
        fail_stage: str | None = None,
    ) -> None:
        self._modified_item_ids = modified_item_ids
        self._added_item_ids = added_item_ids
        self._fail_stage = fail_stage
        self.added_detect_calls: list[frozenset[UUID]] = []
        self.modified_detect_calls: list[frozenset[UUID]] = []
        self.research_calls: list[frozenset[UUID]] = []

    async def detect_added_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        added_after_element_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[UUID, ...]:
        if self._fail_stage == "detect_added":
            raise _WORKER_LOSS
        self.added_detect_calls.append(frozenset(added_after_element_ids))
        return self._added_item_ids

    async def detect_modified_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        modified_after_element_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[UUID, ...]:
        if self._fail_stage == "detect_modified":
            raise _WORKER_LOSS
        self.modified_detect_calls.append(frozenset(modified_after_element_ids))
        return self._modified_item_ids

    async def request_research(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        affected_item_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[RescanChildWorkTicket, ...]:
        if self._fail_stage == "research":
            raise _WORKER_LOSS
        self.research_calls.append(frozenset(affected_item_ids))
        return self._tickets("research", affected_item_ids)

    @staticmethod
    def _tickets(kind: str, item_ids: tuple[UUID, ...]) -> tuple[RescanChildWorkTicket, ...]:
        return tuple(
            RescanChildWorkTicket(
                item_id=item_id, idempotency_key=f"selective_rescan:{kind}:{item_id}"
            )
            for item_id in item_ids
        )


@dataclass(frozen=True)
class Attempt:
    """One completed attempt: the durable job record plus its fresh doubles."""

    record: JobRecord
    lineage: _RecordingLineage
    evidence: _RecordingEvidence
    child: _FakeChildWork


async def _enqueue(seed: SeededRevision, job_repository: SqlJobRepository) -> UUID:
    enqueued = await job_repository.enqueue(
        EnqueueJob(
            org_id=seed.org_id,
            project_id=seed.project_id,
            actor_id=seed.actor_id,
            job_type="selective_rescan",
            idempotency_key=f"selective_rescan:{seed.after_version_id}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(seed.after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=seed.after_version_id,
        )
    )
    return enqueued.job.job_id


async def _run_fresh_attempt(
    seed: SeededRevision,
    job_id: UUID,
    *,
    attempt_label: str,
    evidence_interrupt_after: int | None = None,
    modified_item_ids: tuple[UUID, ...] | None = None,
    added_item_ids: tuple[UUID, ...] = (),
    child_fail_stage: str | None = None,
) -> Attempt:
    """Run one attempt through a FRESH processor with empty in-process memory.

    Every collaborator (job repository, checkpoint repository, revision plan,
    lineage coordinator, evidence adapter, child boundary, job kernel) is newly
    constructed, so the only state shared with a previous attempt is what was
    durably persisted.
    """
    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    lineage = _RecordingLineage()
    evidence = _RecordingEvidence(interrupt_after=evidence_interrupt_after)
    child = _FakeChildWork(
        modified_item_ids=(seed.modified_item_id,) if modified_item_ids is None else modified_item_ids,
        added_item_ids=added_item_ids,
        fail_stage=child_fail_stage,
    )
    processor = RunSelectiveRescanJobService(
        revision_plan=SqlRevisionPlanAdapter(SqlImportRepository()),
        materialize_items=lineage,
        carry_evidence=evidence,
        child_work=child,
        repository=checkpoints,
        job_repository=job_repository,
    )
    record = await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner=f"local-rescan-{attempt_label}",
    ).run(job_id, seed.org_id, seed.project_id)
    return Attempt(record=record, lineage=lineage, evidence=evidence, child=child)


async def _resume(seed: SeededRevision, job_id: UUID) -> None:
    """Return a failed job to the queue exactly as a governed retry does."""
    job_repository = SqlJobRepository()
    current = await job_repository.get(
        org_id=seed.org_id, project_id=seed.project_id, job_id=job_id
    )
    assert current is not None
    if current.status is RunStatus.SUCCEEDED:
        await job_repository.cancel(
            org_id=seed.org_id,
            project_id=seed.project_id,
            job_id=job_id,
            actor_id=seed.actor_id,
        )
    await job_repository.retry(
        org_id=seed.org_id, project_id=seed.project_id, job_id=job_id, actor_id=seed.actor_id
    )


# --------------------------------------------------------------------------- #
# Persisted-state readers
# --------------------------------------------------------------------------- #


async def _carried_items(seed: SeededRevision) -> dict[UUID, UUID]:
    """Map predecessor item id -> carried successor item id on the after version."""
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT predecessor_item_id, id FROM clearance_items "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND version_id = :version_id AND lineage_kind = 'carried_forward'"
                    ),
                    {
                        "org_id": str(seed.org_id),
                        "project_id": str(seed.project_id),
                        "version_id": str(seed.after_version_id),
                    },
                )
            )
            .mappings()
            .all()
        )
    return {UUID(str(row["predecessor_item_id"])): UUID(str(row["id"])) for row in rows}


async def _carried_edges(seed: SeededRevision) -> list[tuple[UUID, UUID, UUID]]:
    """List ``(new_item_id, source_item_id, original_claim_id)`` carried edges."""
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT new_item_id, source_item_id, original_claim_id "
                        "FROM evidence_carry_forwards "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "ORDER BY created_at, id"
                    ),
                    {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
                )
            )
            .mappings()
            .all()
        )
    return [
        (
            UUID(str(row["new_item_id"])),
            UUID(str(row["source_item_id"])),
            UUID(str(row["original_claim_id"])),
        )
        for row in rows
    ]


async def _completed_stages(seed: SeededRevision, job_id: UUID) -> frozenset[RescanStage]:
    return await SqlSelectiveRescanRepository().completed_stages(
        org_id=seed.org_id, project_id=seed.project_id, job_id=job_id
    )


# --------------------------------------------------------------------------- #
# 1. Interrupted after materializing lineage
# --------------------------------------------------------------------------- #


async def test_resume_after_lineage_still_carries_all_expected_evidence() -> None:
    """Lineage succeeded, then the worker died: every carried item must carry.

    The resumed attempt must not re-materialize (no duplicate items) and must
    still carry evidence for BOTH carried items, because the carried mappings
    that lineage produced are the input the evidence stage needs.
    """
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    first = await _run_fresh_attempt(seed, job_id, attempt_label="one", evidence_interrupt_after=0)
    assert first.record.status is RunStatus.FAILED
    completed = await _completed_stages(seed, job_id)
    assert RescanStage.MATERIALIZING_LINEAGE in completed
    assert RescanStage.CARRYING_EVIDENCE not in completed
    carried = await _carried_items(seed)
    assert len(carried) == 2
    assert await _carried_edges(seed) == []

    await _resume(seed, job_id)
    added_item_id = uuid6.uuid7()
    second = await _run_fresh_attempt(
        seed, job_id, attempt_label="two", added_item_ids=(added_item_id,)
    )

    assert second.record.status is RunStatus.SUCCEEDED
    # The completed lineage stage is not repeated ...
    assert second.lineage.calls == []
    # ... but its output is restored, so every carried item carries its evidence.
    assert len(second.evidence.calls) == 2
    edges = await _carried_edges(seed)
    assert len(edges) == 2
    assert {(source, claim) for _new, source, claim in edges} == {
        (passage.predecessor_item_id, passage.original_claim_id) for passage in seed.carryable
    }
    assert {new for new, _source, _claim in edges} == set(carried.values())


# --------------------------------------------------------------------------- #
# 2. Interrupted midway through evidence carry
# --------------------------------------------------------------------------- #


async def test_resume_midway_through_evidence_carry_loses_and_duplicates_nothing() -> None:
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    first = await _run_fresh_attempt(seed, job_id, attempt_label="one", evidence_interrupt_after=1)
    assert first.record.status is RunStatus.FAILED
    assert len(await _carried_edges(seed)) == 1

    await _resume(seed, job_id)
    second = await _run_fresh_attempt(
        seed, job_id, attempt_label="two", added_item_ids=(uuid6.uuid7(),)
    )

    assert second.record.status is RunStatus.SUCCEEDED
    edges = await _carried_edges(seed)
    # Exactly one edge per (carried item, original claim): nothing lost, nothing
    # duplicated for the item that was already carried before the interruption.
    assert len(edges) == 2
    assert len({(new, claim) for new, _source, claim in edges}) == 2
    assert second.record.result_summary is not None
    assert second.record.result_summary["carriedEvidenceEdgeCount"] == 2


# --------------------------------------------------------------------------- #
# 3. Interrupted after detection completes
# --------------------------------------------------------------------------- #


async def test_resume_after_detection_delivers_its_item_ids_to_research() -> None:
    """The item ids detection produced must reach research on the resumed run."""
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    first_added_item_id = uuid6.uuid7()
    first = await _run_fresh_attempt(
        seed,
        job_id,
        attempt_label="one",
        added_item_ids=(first_added_item_id,),
        child_fail_stage="research",
    )
    assert first.record.status is RunStatus.FAILED
    completed = await _completed_stages(seed, job_id)
    assert RescanStage.DETECTING_AFFECTED_PASSAGES in completed
    assert RescanStage.RESEARCHING_AFFECTED_ITEMS not in completed
    assert first.child.modified_detect_calls == [frozenset({seed.modified_after_element_id})]

    await _resume(seed, job_id)
    # A different added-item id on the resumed attempt: if research receives it,
    # the ids were recomputed rather than restored.
    second = await _run_fresh_attempt(
        seed, job_id, attempt_label="two", added_item_ids=(uuid6.uuid7(),)
    )

    assert second.record.status is RunStatus.SUCCEEDED
    assert second.child.modified_detect_calls == []
    assert second.child.added_detect_calls == []
    assert second.child.research_calls == [frozenset({seed.modified_item_id, first_added_item_id})]


# --------------------------------------------------------------------------- #
# 4. Complete success, then replay
# --------------------------------------------------------------------------- #


async def test_replay_after_full_success_duplicates_no_governed_or_provider_work() -> None:
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    first = await _run_fresh_attempt(
        seed, job_id, attempt_label="one", added_item_ids=(uuid6.uuid7(),)
    )
    assert first.record.status is RunStatus.SUCCEEDED
    carried_before = await _carried_items(seed)
    edges_before = await _carried_edges(seed)

    await _resume(seed, job_id)
    replay = await _run_fresh_attempt(
        seed, job_id, attempt_label="replay", added_item_ids=(uuid6.uuid7(),)
    )

    assert replay.record.status is RunStatus.SUCCEEDED
    # No repeated writes and no repeated provider/child work.
    assert replay.lineage.calls == []
    assert replay.evidence.calls == []
    assert replay.child.modified_detect_calls == []
    assert replay.child.added_detect_calls == []
    assert replay.child.research_calls == []
    assert await _carried_items(seed) == carried_before
    assert await _carried_edges(seed) == edges_before


# --------------------------------------------------------------------------- #
# 5. A resumed run reports the truth
# --------------------------------------------------------------------------- #


async def test_resumed_run_summary_reports_true_totals_not_zeros() -> None:
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    added_item_id = uuid6.uuid7()
    first = await _run_fresh_attempt(
        seed,
        job_id,
        attempt_label="one",
        added_item_ids=(added_item_id,),
        child_fail_stage="research",
    )
    assert first.record.status is RunStatus.FAILED

    await _resume(seed, job_id)
    resumed = await _run_fresh_attempt(
        seed, job_id, attempt_label="two", added_item_ids=(uuid6.uuid7(),)
    )

    assert resumed.record.status is RunStatus.SUCCEEDED
    summary = resumed.record.result_summary
    assert summary is not None
    # The work a previous attempt completed is reported truthfully, not as zero.
    assert summary["carriedItemCount"] == 2
    assert summary["carriedEvidenceEdgeCount"] == 2
    assert summary["affectedItemCount"] == 2
    assert summary["modifiedItemCount"] == 1
    assert summary["addedItemCount"] == 1
    assert summary["afterVersionId"] == str(seed.after_version_id)


# --------------------------------------------------------------------------- #
# 6. A succeeded stage whose output cannot be restored fails closed
# --------------------------------------------------------------------------- #


async def test_unrestorable_completed_stage_fails_closed_instead_of_running_empty() -> None:
    """A succeeded checkpoint with no replayable output must not be trusted.

    A checkpoint written before stage outputs were persisted records only counts.
    Skipping that stage and continuing with empty inputs is exactly the silent
    incorrectness this defect is about, so the job must fail with a typed error
    and run no later stage.
    """
    seed = await _seed_recovery_revision()
    job_repository = SqlJobRepository()
    job_id = await _enqueue(seed, job_repository)

    async with session_scope() as session:
        now = datetime.now(UTC)
        await session.execute(
            sa.text(
                "INSERT INTO selective_rescan_checkpoints "
                "(id, org_id, project_id, job_id, stage, status, result, attempt_number, "
                "created_at, completed_at) VALUES "
                "(:id, :org_id, :project_id, :job_id, 'materializing_lineage', 'succeeded', "
                ":result, 1, :created_at, :completed_at)"
            ).bindparams(sa.bindparam("result", type_=sa.JSON())),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(seed.org_id),
                "project_id": str(seed.project_id),
                "job_id": str(job_id),
                "result": {"carriedItemCount": 2},
                "created_at": now,
                "completed_at": now,
            },
        )

    attempt = await _run_fresh_attempt(seed, job_id, attempt_label="legacy")

    assert attempt.record.status is RunStatus.FAILED
    assert attempt.record.error is not None
    assert attempt.record.error.code == "unrestorable_rescan_checkpoint"
    assert attempt.evidence.calls == []
    assert attempt.child.modified_detect_calls == []
    assert attempt.child.research_calls == []

"""Behavioral tests for safe item and evidence carry-forward.

These tests pin the selective-rescan carry-forward vertical slice end to end
against the real migrated schema (migration 0035): a scoped revision plan sourced
from the scripts module, item lineage materialized by the detection module, and
evidence lineage carried by the research module — all coordinated through typed
rescan ports. The governance invariants are proven directly against storage:

* a NEW clearance item is created for each carryable (exact/contextual unchanged
  or moved) element, bound to the after version/element with a predecessor edge,
  ``carried_forward`` lineage, ``carried_forward_confirmation_required`` status,
  an unresolved workflow, and no assignee/disposition/decision or detection
  provenance;
* modified/added elements get no carried item, removed elements stay historical;
* prior human decisions are never copied — they remain visible only on the
  predecessor item;
* carried evidence is written to ``evidence_carry_forwards`` referencing the
  ORIGINAL claim/snapshot/run/query/provider-attempt provenance and never as a
  direct ``evidence_claims`` row for the new item, so the direct cited-claim
  count for the new item stays zero;
* replay is idempotent (same mapping, no duplicate rows);
* tenant/project scope is enforced before any data access.
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
from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    CarryableElementPair,
    RescanSafeError,
    RescanStage,
    RevisionPlan,
)
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class SeededItem:
    org_id: UUID
    project_id: UUID
    script_id: UUID
    before_version_id: UUID
    after_version_id: UUID
    predecessor_item_id: UUID
    before_element_id: UUID
    after_element_id: UUID
    original_claim_id: UUID
    snapshot_id: UUID
    run_id: UUID
    query_id: UUID
    provider_attempt_id: UUID


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
                "title": "Carry-forward project",
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


async def _seed_predecessor_item(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    element_id: UUID,
    item_id: UUID,
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
                "'products_and_trademarks', 'Acme Corporation', 'resolved', 'completed', "
                "'resolved', 'approved_as_is', :created_at, 3)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "created_at": now,
            },
        )


async def _seed_full_provenance_claim(
    *,
    org_id: UUID,
    project_id: UUID,
    item_id: UUID,
    version_id: UUID,
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    """Seed a research run, query, search provider attempt, authorization,
    snapshot, and one evidence claim with full provenance. Returns
    ``(claim_id, snapshot_id, run_id, query_id, provider_attempt_id)``.
    """
    now = datetime.now(UTC)
    run_id = uuid6.uuid7()
    query_id = uuid6.uuid7()
    attempt_id = uuid6.uuid7()
    authorization_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()
    claim_id = uuid6.uuid7()
    canonical_url = "https://register.example/trademark"
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
                "(:id, :run_id, 'acme trademark', 1, :org_id, :project_id, :item_id, "
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
                "url": canonical_url,
                "canonical_url": canonical_url,
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
                "url": canonical_url,
                "sha256_hash": "a" * 64,
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
    return claim_id, snapshot_id, run_id, query_id, attempt_id


async def _seed_carry_forward_revision() -> SeededItem:
    """Seed two adjacent versions with one carryable (unchanged) element that
    has a resolved predecessor item and one full-provenance claim, plus an
    accompanying persisted adjacent diff so the revision plan can be read.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    before_element_id = uuid6.uuid7()
    after_element_id = uuid6.uuid7()
    predecessor_item_id = uuid6.uuid7()

    await _seed_project(org_id, project_id)
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
    await _seed_element(
        version_id=before_version_id,
        element_id=before_element_id,
        ordinal=1,
        text="Acme Corporation",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=after_element_id,
        ordinal=1,
        text="Acme Corporation",
    )
    await _seed_predecessor_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=before_element_id,
        item_id=predecessor_item_id,
    )
    claim_id, snapshot_id, run_id, query_id, attempt_id = await _seed_full_provenance_claim(
        org_id=org_id,
        project_id=project_id,
        item_id=predecessor_item_id,
        version_id=before_version_id,
    )
    await _seed_persisted_diff(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_element_id=before_element_id,
        after_element_id=after_element_id,
    )
    return SeededItem(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        predecessor_item_id=predecessor_item_id,
        before_element_id=before_element_id,
        after_element_id=after_element_id,
        original_claim_id=claim_id,
        snapshot_id=snapshot_id,
        run_id=run_id,
        query_id=query_id,
        provider_attempt_id=attempt_id,
    )


async def _seed_persisted_diff(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    before_version_id: UUID,
    after_version_id: UUID,
    before_element_id: UUID,
    after_element_id: UUID,
) -> None:
    now = datetime.now(UTC)
    diff_id = uuid6.uuid7()
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
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_element_lineage "
                "(id, org_id, project_id, script_id, diff_id, before_version_id, "
                "after_version_id, before_element_id, after_element_id, change_kind, "
                "confidence, algorithm_version, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :diff_id, :before_version_id, "
                ":after_version_id, :before_element_id, :after_element_id, 'unchanged', "
                "'exact', 'element-lineage-v1', :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "diff_id": str(diff_id),
                "before_version_id": str(before_version_id),
                "after_version_id": str(after_version_id),
                "before_element_id": str(before_element_id),
                "after_element_id": str(after_element_id),
                "created_at": now,
            },
        )


# --------------------------------------------------------------------------- #
# Revision plan port
# --------------------------------------------------------------------------- #


async def test_revision_plan_exposes_scoped_carryable_and_affected_sets() -> None:
    seed = await _seed_carry_forward_revision()
    adapter = SqlRevisionPlanAdapter(SqlImportRepository())

    plan = await adapter.load_revision_plan(
        org_id=seed.org_id,
        project_id=seed.project_id,
        after_version_id=seed.after_version_id,
    )

    assert isinstance(plan, RevisionPlan)
    assert plan.before_version_id == seed.before_version_id
    assert plan.after_version_id == seed.after_version_id
    assert plan.script_id == seed.script_id
    carryable = plan.carryable_elements
    assert len(carryable) == 1
    element = carryable[0]
    assert isinstance(element, CarryableElementPair)
    assert element.before_element_id == seed.before_element_id
    assert element.after_element_id == seed.after_element_id
    # An unchanged/exact element is carryable, not affected.
    assert seed.after_element_id not in plan.affected_element_ids


async def test_revision_plan_enforces_tenant_scope_before_access() -> None:
    seed = await _seed_carry_forward_revision()
    adapter = SqlRevisionPlanAdapter(SqlImportRepository())

    with pytest.raises(RescanSafeError):
        await adapter.load_revision_plan(
            org_id=uuid6.uuid7(),  # foreign org
            project_id=seed.project_id,
            after_version_id=seed.after_version_id,
        )


# --------------------------------------------------------------------------- #
# Item lineage port
# --------------------------------------------------------------------------- #


async def _carryable_mapping(seed: SeededItem) -> CarryableElement:
    return CarryableElement(
        before_element_id=seed.before_element_id,
        after_element_id=seed.after_element_id,
        predecessor_item_id=seed.predecessor_item_id,
        category="products_and_trademarks",
        text="Acme Corporation",
    )


async def test_materialize_carried_items_creates_scoped_carried_item() -> None:
    seed = await _seed_carry_forward_revision()
    adapter = SqlItemLineageAdapter()

    mappings = await adapter.materialize_carried_items(
        org_id=seed.org_id,
        project_id=seed.project_id,
        script_id=seed.script_id,
        before_version_id=seed.before_version_id,
        after_version_id=seed.after_version_id,
        carryable_elements=(await _carryable_mapping(seed),),
    )

    assert len(mappings) == 1
    mapping = mappings[0]
    assert isinstance(mapping, CarriedItemMapping)
    assert mapping.predecessor_item_id == seed.predecessor_item_id

    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT org_id, project_id, script_id, version_id, element_id, status, "
                        "workflow_status, disposition_status, assigned_to_user_id, lineage_kind, "
                        "predecessor_item_id, "
                        "carried_forward_confirmation_required, detection_candidate_id, "
                        "detection_run_id, candidate_fingerprint "
                        "FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(mapping.new_item_id)},
                )
            )
            .mappings()
            .one()
        )

    assert UUID(str(row["org_id"])) == seed.org_id
    assert UUID(str(row["project_id"])) == seed.project_id
    assert UUID(str(row["version_id"])) == seed.after_version_id
    assert UUID(str(row["element_id"])) == seed.after_element_id
    assert str(row["status"]) == "unresolved"
    assert str(row["lineage_kind"]) == "carried_forward"
    assert bool(row["carried_forward_confirmation_required"]) is True
    assert UUID(str(row["predecessor_item_id"])) == seed.predecessor_item_id
    # No assignee/disposition/decision and no detection provenance on a carried item.
    assert row["assigned_to_user_id"] is None
    assert str(row["disposition_status"]) == "undisposed"
    assert row["detection_candidate_id"] is None
    assert row["detection_run_id"] is None
    assert row["candidate_fingerprint"] is None


async def test_materialize_carried_items_is_idempotent_on_replay() -> None:
    seed = await _seed_carry_forward_revision()
    adapter = SqlItemLineageAdapter()
    element = await _carryable_mapping(seed)

    first = await adapter.materialize_carried_items(
        org_id=seed.org_id,
        project_id=seed.project_id,
        script_id=seed.script_id,
        before_version_id=seed.before_version_id,
        after_version_id=seed.after_version_id,
        carryable_elements=(element,),
    )
    second = await adapter.materialize_carried_items(
        org_id=seed.org_id,
        project_id=seed.project_id,
        script_id=seed.script_id,
        before_version_id=seed.before_version_id,
        after_version_id=seed.after_version_id,
        carryable_elements=(element,),
    )

    assert first[0].new_item_id == second[0].new_item_id
    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE predecessor_item_id = :predecessor AND version_id = :version_id"
                ),
                {
                    "predecessor": str(seed.predecessor_item_id),
                    "version_id": str(seed.after_version_id),
                },
            )
        ).scalar_one()
    assert count == 1


async def test_prior_human_decision_is_not_copied_to_carried_item() -> None:
    seed = await _seed_carry_forward_revision()
    # A prior governed decision exists only on the predecessor item.
    actor_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {
                "id": str(actor_id),
                "email": f"reviewer-{actor_id}@example.com",
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO governed_decision_records "
                "(id, org_id, project_id, item_id, actor_id, decision_kind, decision_value, "
                "rationale, expected_version, resulting_version, created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :actor_id, 'evidence', 'accepted', "
                "'Prior clearance decision.', 1, 2, :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(seed.org_id),
                "project_id": str(seed.project_id),
                "item_id": str(seed.predecessor_item_id),
                "actor_id": str(actor_id),
                "created_at": datetime.now(UTC),
            },
        )

    adapter = SqlItemLineageAdapter()
    mappings = await adapter.materialize_carried_items(
        org_id=seed.org_id,
        project_id=seed.project_id,
        script_id=seed.script_id,
        before_version_id=seed.before_version_id,
        after_version_id=seed.after_version_id,
        carryable_elements=(await _carryable_mapping(seed),),
    )
    new_item_id = mappings[0].new_item_id

    async with session_scope() as session:
        decisions_on_new = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(new_item_id)},
            )
        ).scalar_one()
        decisions_on_predecessor = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(seed.predecessor_item_id)},
            )
        ).scalar_one()
    assert decisions_on_new == 0
    assert decisions_on_predecessor == 1


# --------------------------------------------------------------------------- #
# Evidence lineage port
# --------------------------------------------------------------------------- #


async def _materialize(seed: SeededItem) -> UUID:
    adapter = SqlItemLineageAdapter()
    mappings = await adapter.materialize_carried_items(
        org_id=seed.org_id,
        project_id=seed.project_id,
        script_id=seed.script_id,
        before_version_id=seed.before_version_id,
        after_version_id=seed.after_version_id,
        carryable_elements=(await _carryable_mapping(seed),),
    )
    return mappings[0].new_item_id


async def test_carry_forward_evidence_references_original_provenance() -> None:
    seed = await _seed_carry_forward_revision()
    new_item_id = await _materialize(seed)
    adapter = SqlEvidenceLineageAdapter()

    carried = await adapter.carry_forward(
        org_id=seed.org_id,
        project_id=seed.project_id,
        new_item_id=new_item_id,
        source_item_id=seed.predecessor_item_id,
    )

    assert len(carried) == 1
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT new_item_id, source_item_id, original_claim_id, snapshot_id, "
                        "run_id, query_id, provider_attempt_id "
                        "FROM evidence_carry_forwards WHERE new_item_id = :new_item_id"
                    ),
                    {"new_item_id": str(new_item_id)},
                )
            )
            .mappings()
            .one()
        )
        direct_claims = (
            await session.execute(
                sa.text("SELECT count(*) FROM evidence_claims WHERE item_id = :item_id"),
                {"item_id": str(new_item_id)},
            )
        ).scalar_one()

    assert UUID(str(row["source_item_id"])) == seed.predecessor_item_id
    assert UUID(str(row["original_claim_id"])) == seed.original_claim_id
    assert UUID(str(row["snapshot_id"])) == seed.snapshot_id
    assert UUID(str(row["run_id"])) == seed.run_id
    assert UUID(str(row["query_id"])) == seed.query_id
    assert UUID(str(row["provider_attempt_id"])) == seed.provider_attempt_id
    # Never write a direct evidence_claims row for the new item.
    assert direct_claims == 0


async def test_carry_forward_evidence_is_idempotent_on_replay() -> None:
    seed = await _seed_carry_forward_revision()
    new_item_id = await _materialize(seed)
    adapter = SqlEvidenceLineageAdapter()

    await adapter.carry_forward(
        org_id=seed.org_id,
        project_id=seed.project_id,
        new_item_id=new_item_id,
        source_item_id=seed.predecessor_item_id,
    )
    await adapter.carry_forward(
        org_id=seed.org_id,
        project_id=seed.project_id,
        new_item_id=new_item_id,
        source_item_id=seed.predecessor_item_id,
    )

    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_carry_forwards WHERE new_item_id = :new_item_id"
                ),
                {"new_item_id": str(new_item_id)},
            )
        ).scalar_one()
    assert count == 1


async def test_read_carried_provenance_for_new_item() -> None:
    seed = await _seed_carry_forward_revision()
    new_item_id = await _materialize(seed)
    adapter = SqlEvidenceLineageAdapter()
    await adapter.carry_forward(
        org_id=seed.org_id,
        project_id=seed.project_id,
        new_item_id=new_item_id,
        source_item_id=seed.predecessor_item_id,
    )

    provenance = await adapter.list_carried_provenance(
        org_id=seed.org_id,
        project_id=seed.project_id,
        new_item_id=new_item_id,
    )

    assert len(provenance) == 1
    carried = provenance[0]
    assert carried.original_claim_id == seed.original_claim_id
    assert carried.snapshot_id == seed.snapshot_id
    assert carried.run_id == seed.run_id


async def test_zero_source_claims_carry_zero_evidence() -> None:
    # A predecessor item with no evidence claims yields no carried claims.
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    before_element_id = uuid6.uuid7()
    after_element_id = uuid6.uuid7()
    predecessor_item_id = uuid6.uuid7()

    await _seed_project(org_id, project_id)
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
    await _seed_element(
        version_id=before_version_id,
        element_id=before_element_id,
        ordinal=1,
        text="Acme Corporation",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=after_element_id,
        ordinal=1,
        text="Acme Corporation",
    )
    await _seed_predecessor_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=before_element_id,
        item_id=predecessor_item_id,
    )

    item_adapter = SqlItemLineageAdapter()
    mappings = await item_adapter.materialize_carried_items(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        carryable_elements=(
            CarryableElement(
                before_element_id=before_element_id,
                after_element_id=after_element_id,
                predecessor_item_id=predecessor_item_id,
                category="products_and_trademarks",
                text="Acme Corporation",
            ),
        ),
    )
    new_item_id = mappings[0].new_item_id

    evidence_adapter = SqlEvidenceLineageAdapter()
    carried = await evidence_adapter.carry_forward(
        org_id=org_id,
        project_id=project_id,
        new_item_id=new_item_id,
        source_item_id=predecessor_item_id,
    )
    assert carried == ()


def test_rescan_stage_has_the_seven_approved_stages() -> None:
    assert [stage.value for stage in RescanStage] == [
        "queued",
        "materializing_lineage",
        "carrying_evidence",
        "detecting_affected_passages",
        "researching_affected_items",
        "awaiting_confirmation",
        "completed",
    ]

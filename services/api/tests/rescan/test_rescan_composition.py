"""Composition tests: every clearance item on a carried passage survives rescan.

Defect D4 — a screenplay passage can hold MORE THAN ONE clearance item (two
brands on one action line, a brand plus a landmark, the same entity named twice).
The selective-rescan item-lineage coordinator resolved the predecessor item for a
carryable element with a single-row read, so a passage with N items carried only
one of them: the remaining findings were silently dropped from the new version
with no error and no visible review item.

These tests pin the composition contract against the REAL coordinator and REAL
database persistence (migrated schema, no mocked storage):

* every scoped predecessor item on a carried passage produces exactly one carried
  successor item, in a deterministic order;
* distinct findings are never deduplicated by passage text or category — two
  brands on one line are two findings, and the same entity named twice is two
  findings;
* an item-less carryable passage carries nothing and raises nothing;
* a MOVED (not modified) passage carries its full item set;
* repeated materialization is idempotent — the same mappings, no duplicate rows;
* each carried item keeps its OWN evidence provenance;
* no prior human decision is carried forward and no carried item implies
  clearance in the new version.
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
from clearcut.rescan.application.models import CarryableElement
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter

pytestmark = pytest.mark.asyncio

_PASSAGE_TEXT = "Vera pops a Coke, checks her Rolex, then crosses the Brooklyn Bridge."


@dataclass(frozen=True)
class SeededFinding:
    """One predecessor clearance item plus its own full-provenance claim."""

    item_id: UUID
    category: str
    text: str
    claim_id: UUID
    snapshot_id: UUID
    run_id: UUID
    query_id: UUID
    provider_attempt_id: UUID


@dataclass(frozen=True)
class SeededPassage:
    """Two adjacent versions sharing one carried passage with N findings."""

    org_id: UUID
    project_id: UUID
    script_id: UUID
    before_version_id: UUID
    after_version_id: UUID
    before_element_id: UUID
    after_element_id: UUID
    findings: tuple[SeededFinding, ...]

    @property
    def predecessor_item_ids(self) -> set[UUID]:
        return {finding.item_id for finding in self.findings}

    def carryable(self) -> tuple[CarryableElement, ...]:
        """The element-only carryable pair the orchestration hands the coordinator.

        ``RunSelectiveRescanJobService`` publishes ONE carryable element per
        diffed element pair and uses ``before_element_id`` as the join key in the
        ``predecessor_item_id`` slot; the coordinator resolves the real
        predecessor items. A passage with N items still arrives as one pair.
        """
        return (
            CarryableElement(
                before_element_id=self.before_element_id,
                after_element_id=self.after_element_id,
                predecessor_item_id=self.before_element_id,
                category="",
                text=_PASSAGE_TEXT,
            ),
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
                "title": "Multi-item passage project",
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


async def _seed_resolved_item(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    element_id: UUID,
    item_id: UUID,
    category: str,
    text: str,
) -> None:
    """A predecessor item that a human already resolved and approved as-is."""
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, :category, "
                ":text, 'resolved', 'completed', 'resolved', 'approved_as_is', :created_at, 3)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "category": category,
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
    ordinal: int,
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    """Seed one item's own research run, query, attempt, snapshot, and claim.

    Each finding gets DISTINCT provenance (distinct url, hash, and claim text) so
    a carried item that borrowed a sibling's evidence would be visible.
    """
    now = datetime.now(UTC)
    run_id = uuid6.uuid7()
    query_id = uuid6.uuid7()
    attempt_id = uuid6.uuid7()
    authorization_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()
    claim_id = uuid6.uuid7()
    canonical_url = f"https://register.example/mark-{ordinal}"
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
                "(:id, :run_id, :query, 1, :org_id, :project_id, :item_id, :version_id, "
                ":created_at)"
            ),
            {
                "id": str(query_id),
                "run_id": str(run_id),
                "query": f"trademark search {ordinal}",
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
                "'search', 1, :url, :canonical_url, :title, 'USPTO', :excerpt, :created_at)"
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
                "title": f"Official register {ordinal}",
                "excerpt": f"Register entry {ordinal}.",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                "origin, sha256_hash, retrieved_at, query_id, provider_attempt_id, "
                "authorization_id, authorizing_search_attempt_id) VALUES "
                "(:id, :org_id, :project_id, :item_id, :run_id, :url, :title, 'USPTO', "
                ":excerpt, 'search', :sha256_hash, :retrieved_at, :query_id, "
                ":provider_attempt_id, :authorization_id, :authorizing_search_attempt_id)"
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "url": canonical_url,
                "title": f"Official register {ordinal}",
                "excerpt": f"Register entry {ordinal}.",
                "sha256_hash": f"{ordinal:064d}",
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
                "claim_text": f"Register entry {ordinal} shows no conflicting active mark.",
                "excerpt": f"Register entry {ordinal}.",
                "created_at": now,
                "run_id": str(run_id),
                "query_id": str(query_id),
                "provider_attempt_id": str(attempt_id),
            },
        )
    return claim_id, snapshot_id, run_id, query_id, attempt_id


async def _seed_persisted_diff(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    before_version_id: UUID,
    after_version_id: UUID,
    before_element_id: UUID,
    after_element_id: UUID,
    change_kind: str,
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
                ":after_version_id, :before_element_id, :after_element_id, :change_kind, "
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
                "change_kind": change_kind,
                "created_at": now,
            },
        )


async def _seed_passage(
    *,
    findings: tuple[tuple[str, str], ...],
    change_kind: str = "unchanged",
    with_evidence: bool = True,
) -> SeededPassage:
    """Seed one carried passage holding ``findings`` (category, text) items.

    Item ids are minted in sequence so the expected carry order is the seeded
    order; every item gets its own distinct full-provenance claim.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    before_element_id = uuid6.uuid7()
    after_element_id = uuid6.uuid7()

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
        text=_PASSAGE_TEXT,
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=after_element_id,
        # A MOVED passage keeps its text and changes ordinal; an unchanged
        # passage keeps both. Either way the item set must carry in full.
        ordinal=1 if change_kind == "unchanged" else 7,
        text=_PASSAGE_TEXT,
    )

    seeded: list[SeededFinding] = []
    for ordinal, (category, text) in enumerate(findings, start=1):
        item_id = uuid6.uuid7()
        await _seed_resolved_item(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=before_version_id,
            element_id=before_element_id,
            item_id=item_id,
            category=category,
            text=text,
        )
        if with_evidence:
            claim_id, snapshot_id, run_id, query_id, attempt_id = (
                await _seed_full_provenance_claim(
                    org_id=org_id,
                    project_id=project_id,
                    item_id=item_id,
                    version_id=before_version_id,
                    ordinal=ordinal,
                )
            )
        else:
            claim_id = snapshot_id = run_id = query_id = attempt_id = uuid6.uuid7()
        seeded.append(
            SeededFinding(
                item_id=item_id,
                category=category,
                text=text,
                claim_id=claim_id,
                snapshot_id=snapshot_id,
                run_id=run_id,
                query_id=query_id,
                provider_attempt_id=attempt_id,
            )
        )

    await _seed_persisted_diff(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_element_id=before_element_id,
        after_element_id=after_element_id,
        change_kind=change_kind,
    )
    return SeededPassage(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_element_id=before_element_id,
        after_element_id=after_element_id,
        findings=tuple(seeded),
    )


def _coordinator() -> _SelectiveRescanItemLineageCoordinator:
    return _SelectiveRescanItemLineageCoordinator(SqlItemLineageAdapter())


async def _materialize(passage: SeededPassage):
    return await _coordinator().materialize(
        org_id=passage.org_id,
        project_id=passage.project_id,
        script_id=passage.script_id,
        before_version_id=passage.before_version_id,
        after_version_id=passage.after_version_id,
        carryable_elements=passage.carryable(),
    )


# --------------------------------------------------------------------------- #
# D4 — every item on a carried passage survives
# --------------------------------------------------------------------------- #


async def test_two_items_on_one_unchanged_passage_both_carry_forward() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("products_and_trademarks", "Rolex"),
        )
    )
    expected_predecessor_ids = passage.predecessor_item_ids

    mappings = await _materialize(passage)

    assert {m.predecessor_item_id for m in mappings} == expected_predecessor_ids
    assert len({m.new_item_id for m in mappings}) == len(expected_predecessor_ids)
    # Both successors are bound to the SAME after element: two findings on one line.
    assert {m.after_element_id for m in mappings} == {passage.after_element_id}
    assert {m.after_version_id for m in mappings} == {passage.after_version_id}

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id, predecessor_item_id, category, text, element_id "
                        "FROM clearance_items "
                        "WHERE org_id = :org_id AND version_id = :version_id "
                        "ORDER BY created_at, id"
                    ),
                    {
                        "org_id": str(passage.org_id),
                        "version_id": str(passage.after_version_id),
                    },
                )
            )
            .mappings()
            .all()
        )

    assert len(rows) == 2
    assert {UUID(str(row["predecessor_item_id"])) for row in rows} == expected_predecessor_ids
    # Category and text are copied per predecessor, never collapsed.
    assert {str(row["text"]) for row in rows} == {"Coca-Cola", "Rolex"}


async def test_carry_order_is_deterministic_across_repeated_runs() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("locations_and_landmarks", "Brooklyn Bridge"),
            ("products_and_trademarks", "Rolex"),
        )
    )

    first = await _materialize(passage)
    second = await _materialize(passage)

    assert [m.predecessor_item_id for m in first] == [m.predecessor_item_id for m in second]
    assert [m.new_item_id for m in first] == [m.new_item_id for m in second]
    # Seeded predecessor ids are time-ordered, so the carry order follows them.
    assert [m.predecessor_item_id for m in first] == [f.item_id for f in passage.findings]


async def test_carryable_passage_with_zero_items_carries_nothing() -> None:
    passage = await _seed_passage(findings=())

    mappings = await _materialize(passage)

    assert mappings == ()
    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE org_id = :org_id AND version_id = :version_id"
                ),
                {
                    "org_id": str(passage.org_id),
                    "version_id": str(passage.after_version_id),
                },
            )
        ).scalar_one()
    assert count == 0


async def test_two_categories_on_one_passage_are_not_deduplicated() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Rolex"),
            ("locations_and_landmarks", "Brooklyn Bridge"),
        )
    )

    mappings = await _materialize(passage)

    assert {m.predecessor_item_id for m in mappings} == passage.predecessor_item_ids
    async with session_scope() as session:
        categories = (
            await session.execute(
                sa.text(
                    "SELECT category FROM clearance_items "
                    "WHERE org_id = :org_id AND version_id = :version_id"
                ),
                {
                    "org_id": str(passage.org_id),
                    "version_id": str(passage.after_version_id),
                },
            )
        ).scalars()
    assert sorted(str(category) for category in categories) == [
        "locations_and_landmarks",
        "products_and_trademarks",
    ]


async def test_same_entity_named_twice_carries_two_items() -> None:
    # Identical category AND identical text: still two distinct findings, because
    # each is a separately reviewable clearance item with its own evidence.
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Rolex"),
            ("products_and_trademarks", "Rolex"),
        )
    )

    mappings = await _materialize(passage)

    assert {m.predecessor_item_id for m in mappings} == passage.predecessor_item_ids
    assert len({m.new_item_id for m in mappings}) == 2


async def test_moved_passage_carries_every_item() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("products_and_trademarks", "Rolex"),
        ),
        change_kind="moved",
    )
    plan = await SqlRevisionPlanAdapter(SqlImportRepository()).load_revision_plan(
        org_id=passage.org_id,
        project_id=passage.project_id,
        after_version_id=passage.after_version_id,
    )
    # A moved/exact passage is carryable, and the diff still yields ONE pair for
    # the whole passage regardless of how many items it holds.
    assert len(plan.carryable_elements) == 1
    pair = plan.carryable_elements[0]

    mappings = await _coordinator().materialize(
        org_id=passage.org_id,
        project_id=passage.project_id,
        script_id=passage.script_id,
        before_version_id=plan.before_version_id,
        after_version_id=plan.after_version_id,
        carryable_elements=(
            CarryableElement(
                before_element_id=pair.before_element_id,
                after_element_id=pair.after_element_id,
                predecessor_item_id=pair.before_element_id,
                category="",
                text=pair.after_text,
            ),
        ),
    )

    assert {m.predecessor_item_id for m in mappings} == passage.predecessor_item_ids
    assert len({m.new_item_id for m in mappings}) == 2


async def test_repeated_materialization_of_multi_item_passage_is_idempotent() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("products_and_trademarks", "Rolex"),
        )
    )

    first = await _materialize(passage)
    second = await _materialize(passage)

    assert {(m.predecessor_item_id, m.new_item_id) for m in first} == {
        (m.predecessor_item_id, m.new_item_id) for m in second
    }
    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE org_id = :org_id AND version_id = :version_id "
                    "AND lineage_kind = 'carried_forward'"
                ),
                {
                    "org_id": str(passage.org_id),
                    "version_id": str(passage.after_version_id),
                },
            )
        ).scalar_one()
    assert count == 2


# --------------------------------------------------------------------------- #
# Governance — carried evidence keeps provenance and carries no decision
# --------------------------------------------------------------------------- #


async def test_each_carried_item_keeps_its_own_evidence_provenance() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("products_and_trademarks", "Rolex"),
        )
    )
    mappings = await _materialize(passage)
    assert {m.predecessor_item_id for m in mappings} == passage.predecessor_item_ids
    evidence = SqlEvidenceLineageAdapter()
    by_predecessor = {finding.item_id: finding for finding in passage.findings}

    for mapping in mappings:
        carried = await evidence.carry_forward(
            org_id=passage.org_id,
            project_id=passage.project_id,
            new_item_id=mapping.new_item_id,
            source_item_id=mapping.predecessor_item_id,
        )
        assert len(carried) == 1
        provenance = await evidence.list_carried_provenance(
            org_id=passage.org_id,
            project_id=passage.project_id,
            new_item_id=mapping.new_item_id,
        )
        expected = by_predecessor[mapping.predecessor_item_id]
        assert [claim.original_claim_id for claim in provenance] == [expected.claim_id]
        assert [claim.snapshot_id for claim in provenance] == [expected.snapshot_id]
        assert [claim.run_id for claim in provenance] == [expected.run_id]

    async with session_scope() as session:
        direct_claims = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_claims WHERE item_id IN :item_ids"
                ).bindparams(sa.bindparam("item_ids", expanding=True)),
                {"item_ids": [str(m.new_item_id) for m in mappings]},
            )
        ).scalar_one()
    # Carried evidence is a provenance edge, never a fresh cited claim.
    assert direct_claims == 0


async def test_no_human_decision_is_carried_forward_for_any_item() -> None:
    passage = await _seed_passage(
        findings=(
            ("products_and_trademarks", "Coca-Cola"),
            ("products_and_trademarks", "Rolex"),
        )
    )
    actor_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {
                "id": str(actor_id),
                "email": f"reviewer-{actor_id}@example.com",
                "created_at": now,
            },
        )
        for finding in passage.findings:
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
                    "org_id": str(passage.org_id),
                    "project_id": str(passage.project_id),
                    "item_id": str(finding.item_id),
                    "actor_id": str(actor_id),
                    "created_at": now,
                },
            )

    mappings = await _materialize(passage)
    assert len(mappings) == 2

    async with session_scope() as session:
        decisions_on_new = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_decision_records WHERE item_id IN :item_ids"
                ).bindparams(sa.bindparam("item_ids", expanding=True)),
                {"item_ids": [str(m.new_item_id) for m in mappings]},
            )
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, workflow_status, disposition_status, "
                        "assigned_to_user_id, lineage_kind, "
                        "carried_forward_confirmation_required "
                        "FROM clearance_items WHERE id IN :item_ids"
                    ).bindparams(sa.bindparam("item_ids", expanding=True)),
                    {"item_ids": [str(m.new_item_id) for m in mappings]},
                )
            )
            .mappings()
            .all()
        )

    assert decisions_on_new == 0
    assert len(rows) == 2
    for row in rows:
        # No carried item may imply clearance in the new version.
        assert str(row["status"]) == "unresolved"
        assert str(row["workflow_status"]) == "open"
        assert str(row["disposition_status"]) == "undisposed"
        assert row["assigned_to_user_id"] is None
        assert str(row["lineage_kind"]) == "carried_forward"
        assert bool(row["carried_forward_confirmation_required"]) is True

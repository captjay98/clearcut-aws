"""Unit and integration tests for SqlStepReceiptRepository."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.research.adapters.sql_step_receipt_repository import (
    SqlStepReceiptRepository,
)
from clearcut.research.ports.step_receipt_repository import compute_canonical_hash
from sqlalchemy.exc import IntegrityError


async def _seed_test_item_and_run(
    session,
) -> tuple[uuid4, uuid4, uuid4, uuid4, uuid4]:
    """Helper to seed org, project, script, item, and research_run."""
    org_id = uuid4()
    project_id = uuid4()
    script_id = uuid4()
    version_id = uuid4()
    item_id = uuid4()
    run_id = uuid4()

    await session.execute(
        sa.text(
            """
            INSERT INTO organizations (id, name, slug, created_at)
            VALUES (:id, :name, :slug, :created_at)
            """
        ),
        {
            "id": str(org_id),
            "name": "Test Org",
            "slug": f"org-{org_id.hex[:8]}",
            "created_at": datetime.now(UTC),
        },
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO projects (id, org_id, title, created_at)
            VALUES (:id, :org_id, 'Test Project', :created_at)
            """
        ),
        {
            "id": str(project_id),
            "org_id": str(org_id),
            "created_at": datetime.now(UTC),
        },
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO scripts (id, org_id, project_id, title, current_slot, created_at)
            VALUES (:id, :org_id, :project_id, 'Script', 'current', :created_at)
            """
        ),
        {
            "id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "created_at": datetime.now(UTC),
        },
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO script_versions (id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at)
            VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, 'test', :created_at)
            """
        ),
        {
            "id": str(version_id),
            "script_id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "source_hash": "a" * 64,
            "created_at": datetime.now(UTC),
        },
    )
    element_id = uuid4()
    await session.execute(
        sa.text(
            """
            INSERT INTO script_elements (id, version_id, ordinal, element_type, text)
            VALUES (:id, :version_id, 1, 'action', 'Element text')
            """
        ),
        {"id": str(element_id), "version_id": str(version_id)},
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at)
            VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Nike Shoes', 'unresolved', :created_at)
            """
        ),
        {
            "id": str(item_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "script_id": str(script_id),
            "version_id": str(version_id),
            "element_id": str(element_id),
            "created_at": datetime.now(UTC),
        },
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at)
            VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at)
            """
        ),
        {
            "id": str(run_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "item_id": str(item_id),
            "created_at": datetime.now(UTC),
        },
    )
    return org_id, project_id, item_id, run_id, version_id


@pytest.mark.asyncio
async def test_compute_canonical_hash_is_deterministic():
    data1 = {"b": 2, "a": 1, "nested": {"y": "test", "x": 10}}
    data2 = {"a": 1, "nested": {"x": 10, "y": "test"}, "b": 2}
    hash1 = compute_canonical_hash(data1)
    hash2 = compute_canonical_hash(data2)
    assert len(hash1) == 64
    assert hash1 == hash2

    assert compute_canonical_hash(None) == compute_canonical_hash(None)
    assert compute_canonical_hash("search query") != compute_canonical_hash("other query")


@pytest.mark.asyncio
async def test_record_and_get_step_receipt():
    async with session_scope() as session:
        org_id, project_id, item_id, run_id, _ = await _seed_test_item_and_run(session)

    repo = SqlStepReceiptRepository()
    in_hash = compute_canonical_hash({"query": "nike shoes clearance"})
    out_hash = compute_canonical_hash({"snapshots": 3})

    receipt = await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash=in_hash,
        tool_output_hash=out_hash,
        input_payload={"query": "nike shoes clearance"},
        output_payload={"snapshots": 3},
        status="succeeded",
        duration_ms=45,
    )

    assert receipt.org_id == org_id
    assert receipt.project_id == project_id
    assert receipt.run_id == run_id
    assert receipt.item_id == item_id
    assert receipt.step_index == 0
    assert receipt.tool_name == "search_evidence"
    assert receipt.tool_input_hash == in_hash
    assert receipt.tool_output_hash == out_hash
    assert receipt.input_payload == {"query": "nike shoes clearance"}
    assert receipt.output_payload == {"snapshots": 3}
    assert receipt.duration_ms == 45
    assert receipt.created_at.tzinfo is not None

    fetched = await repo.get_receipt(receipt_id=receipt.id)
    assert fetched is not None
    assert fetched.id == receipt.id
    assert fetched.tool_name == "search_evidence"
    assert fetched.input_payload == receipt.input_payload


@pytest.mark.asyncio
async def test_find_replay_receipt():
    async with session_scope() as session:
        org_id, project_id, item_id, run_id, _ = await _seed_test_item_and_run(session)

    repo = SqlStepReceiptRepository()
    in_hash = compute_canonical_hash({"url": "https://example.com/item"})
    out_hash = compute_canonical_hash({"status": "extracted"})

    await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        attempt_number=1,
        step_index=0,
        tool_name="extract_admitted_source",
        tool_input_hash=in_hash,
        tool_output_hash=out_hash,
        input_payload={"url": "https://example.com/item"},
        output_payload={"status": "extracted"},
    )

    replay = await repo.find_replay_receipt(
        run_id=run_id,
        attempt_number=1,
        tool_name="extract_admitted_source",
        tool_input_hash=in_hash,
    )
    assert replay is not None
    assert replay.tool_name == "extract_admitted_source"
    assert replay.output_payload == {"status": "extracted"}

    # Non-matching input hash returns None
    missing = await repo.find_replay_receipt(
        run_id=run_id,
        attempt_number=1,
        tool_name="extract_admitted_source",
        tool_input_hash=compute_canonical_hash({"url": "https://different.com"}),
    )
    assert missing is None


@pytest.mark.asyncio
async def test_list_receipts_and_count_by_tool():
    async with session_scope() as session:
        org_id, project_id, item_id, run_id, _ = await _seed_test_item_and_run(session)

    repo = SqlStepReceiptRepository()

    # Record 3 steps
    await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_index=0,
        tool_name="read_item_context",
        tool_input_hash=compute_canonical_hash({}),
        tool_output_hash=compute_canonical_hash({"context": "ok"}),
    )
    await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_index=1,
        tool_name="search_evidence",
        tool_input_hash=compute_canonical_hash({"q": "query 1"}),
        tool_output_hash=compute_canonical_hash({"results": 1}),
    )
    await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_index=2,
        tool_name="search_evidence",
        tool_input_hash=compute_canonical_hash({"q": "query 2"}),
        tool_output_hash=compute_canonical_hash({"results": 2}),
    )

    receipts = await repo.list_receipts_for_run(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
    )
    assert len(receipts) == 3
    assert [r.step_index for r in receipts] == [0, 1, 2]
    assert [r.tool_name for r in receipts] == [
        "read_item_context",
        "search_evidence",
        "search_evidence",
    ]

    counts = await repo.count_steps_by_tool(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
    )
    assert counts == {
        "read_item_context": 1,
        "search_evidence": 2,
    }

    next_step = await repo.get_next_step_index(run_id=run_id, attempt_number=1)
    assert next_step == 3


@pytest.mark.asyncio
async def test_unique_constraints_prevent_duplicate_steps():
    async with session_scope() as session:
        org_id, project_id, item_id, run_id, _ = await _seed_test_item_and_run(session)

    repo = SqlStepReceiptRepository()
    in_hash = compute_canonical_hash({"query": "dup"})
    out_hash = compute_canonical_hash({"ok": True})

    await repo.record_step(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash=in_hash,
        tool_output_hash=out_hash,
    )

    # 1. Duplicate (run_id, attempt_number, step_index)
    with pytest.raises(IntegrityError):
        await repo.record_step(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_index=0,
            tool_name="plan_queries",
            tool_input_hash=compute_canonical_hash({"other": "input"}),
            tool_output_hash=out_hash,
        )

    # 2. Duplicate (run_id, attempt_number, tool_name, tool_input_hash)
    with pytest.raises(IntegrityError):
        await repo.record_step(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_index=1,
            tool_name="search_evidence",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
        )

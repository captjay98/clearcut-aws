"""Unit and integration tests for DeterministicCompletionValidator."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.research.application.completion_validator import (
    CompletionValidationError,
    DeterministicCompletionValidator,
    MissingMandatorySearchError,
    UnauthenticatedCitationError,
)
from clearcut.research.domain.claims import (
    EvidenceClaim,
    EvidenceStance,
    SourceAuthorityTier,
)
from clearcut.research.ports.step_receipt_repository import StepReceiptRecord


async def _seed_test_run_with_snapshot() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()
    snapshot_id = uuid4()

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org_id),
                "name": "Org",
                "slug": f"org-{org_id.hex[:8]}",
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Title', :created_at)"
            ),
            {"id": str(project_id), "org_id": str(org_id), "created_at": datetime.now(UTC)},
        )
        script_id = uuid4()
        version_id = uuid4()
        element_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, current_slot, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Script', 'current', :created_at)"
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
                "INSERT INTO script_versions (id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
                "VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, 'test', :created_at)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": "c" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Action text.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Test Brand', 'unresolved', :created_at)"
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
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":version_id, 1, 'worker-1', :correlation_id)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "created_at": datetime.now(UTC),
                "version_id": str(version_id),
                "correlation_id": str(uuid4()),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots ("
                "id, org_id, project_id, item_id, run_id, url, title, publisher, "
                "excerpt, origin, sha256_hash, retrieved_at"
                ") VALUES ("
                ":id, :org_id, :project_id, :item_id, :run_id, :url, :title, :publisher, "
                ":excerpt, 'extract', :sha256_hash, :retrieved_at"
                ")"
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "url": "https://official.gov/brand",
                "title": "Official Brand",
                "publisher": "USPTO",
                "excerpt": "Registered trademark details",
                "sha256_hash": "0" * 64,
                "retrieved_at": datetime.now(UTC),
            },
        )
    return org_id, project_id, item_id, run_id, snapshot_id


@pytest.mark.asyncio
async def test_rule_1_mandatory_search_enforcement():
    """Verify that producing claims without executing search_evidence is rejected."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=uuid4(),
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Unsearched claim",
        provenance_excerpt="Excerpt",
    )

    # Empty receipts: no search_evidence executed
    with pytest.raises(MissingMandatorySearchError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[],
            claims=[claim],
        )

    # Failed search receipt also does not satisfy mandatory search
    failed_search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "failed"},
        status="failed",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(MissingMandatorySearchError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[failed_search_receipt],
            claims=[claim],
        )


@pytest.mark.asyncio
async def test_rule_1_mandatory_search_enforced_even_with_zero_claims():
    """Verify that completing a research run without search_evidence is rejected even with 0 claims."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    # Empty receipts with 0 claims raises MissingMandatorySearchError with raise_exc=True
    with pytest.raises(MissingMandatorySearchError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[],
            claims=[],
            raise_exc=True,
        )

    # With raise_exc=False, returns ValidationOutcome(valid=False, error="missing_mandatory_search")
    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[],
        claims=[],
        raise_exc=False,
    )
    assert outcome.valid is False
    assert outcome.error == "missing_mandatory_search"
    assert outcome.reason == "missing_mandatory_search"
    assert outcome.review_status == "unresolved"
    assert outcome.cleared is False
    assert outcome.needs_human_review is True


@pytest.mark.asyncio
async def test_rule_2_rejects_dummy_primitive_claims():
    """Verify that passing dummy primitive objects (like [1]*N) is rejected under Rule 2."""
    org_id, project_id, item_id, run_id, _ = await _seed_test_run_with_snapshot()
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(CompletionValidationError) as exc_info:
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[search_receipt],
            claims=[1, 2, 3],
        )
    assert exc_info.value.code == "invalid_claim"


@pytest.mark.asyncio
async def test_rule_2_authentic_citations_enforcement():
    """Verify cited snapshots must exist in source_snapshots for the scoped run."""
    org_id, project_id, item_id, run_id, valid_snapshot_id = await _seed_test_run_with_snapshot()
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    # Authentic citation passes
    valid_claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=valid_snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Legitimate claim backed by snapshot",
        provenance_excerpt="Registered trademark details",
    )

    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[search_receipt],
        claims=[valid_claim],
    )
    assert outcome.valid is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "human_review_required"

    # Fake citation fails
    fake_snapshot_id = uuid4()
    invalid_claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=fake_snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Fabricated claim",
        provenance_excerpt="Fake excerpt",
    )

    with pytest.raises(UnauthenticatedCitationError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[search_receipt],
            claims=[invalid_claim],
        )


@pytest.mark.asyncio
async def test_rule_3_zero_evidence_unresolved_invariant():
    """Verify zero evidence forces unresolved status, never clearance."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[search_receipt],
        claims=[],
        raw_summary={"cleared": True},
    )

    assert outcome.valid is True
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "no_search_results"


@pytest.mark.asyncio
async def test_rule_4_anti_self_certification():
    """Verify agent summary claiming clearance is strictly overridden by the validator."""
    org_id, project_id, item_id, run_id, valid_snapshot_id = await _seed_test_run_with_snapshot()
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )
    valid_claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=valid_snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Legitimate claim backed by snapshot",
        provenance_excerpt="Registered trademark details",
    )

    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[search_receipt],
        claims=[valid_claim],
        raw_summary={
            "cleared": True,
            "needs_human_review": False,
            "review_status": "cleared",
            "reason": "agent_self_certified",
        },
    )

    # Must be sanitized to human review
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "human_review_required"
    assert outcome.sanitized_summary["cleared"] is False
    assert outcome.sanitized_summary["needs_human_review"] is True


@pytest.mark.asyncio
async def test_rule_5_error_and_refusal_visibility():
    """Verify agent errors or refusals are visible review items, not silent clearance."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[],
        claims=[],
        raw_summary={"refused": True, "error": "Model refused query due to policy"},
    )

    assert outcome.valid is False
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "agent_refusal_or_error"
    assert outcome.error == "Model refused query due to policy"

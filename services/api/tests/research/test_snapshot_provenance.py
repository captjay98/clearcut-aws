import uuid6
from clearcut.research.domain.snapshots import SourceSnapshot


def test_source_snapshot_creation_and_hash():
    snapshot_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    run_id = uuid6.uuid7()

    snapshot = SourceSnapshot.create(
        snapshot_id=snapshot_id,
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=run_id,
        url="https://uspto.gov/trademarks/coca-cola",
        title="USPTO Trademark Database - Coca-Cola",
        publisher="USPTO",
        excerpt="Active trademark registered in 1893 for carbonated soft drinks.",
        origin="search",
        published_date="2024-01-01",
    )

    assert snapshot.url == "https://uspto.gov/trademarks/coca-cola"
    assert snapshot.origin == "search"
    assert len(snapshot.sha256_hash) == 64


def test_carried_evidence_provenance_preserves_original_identity() -> None:
    """The carried-evidence read DTO preserves the original claim, snapshot,
    run, query, and provider-attempt identity verbatim — carry-forward never
    clones snapshot content or invents provider identity.
    """
    from clearcut.rescan.application.models import CarriedEvidenceProvenance

    original_claim_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()
    run_id = uuid6.uuid7()
    query_id = uuid6.uuid7()
    provider_attempt_id = uuid6.uuid7()

    provenance = CarriedEvidenceProvenance(
        original_claim_id=original_claim_id,
        snapshot_id=snapshot_id,
        run_id=run_id,
        query_id=query_id,
        provider_attempt_id=provider_attempt_id,
    )

    assert provenance.original_claim_id == original_claim_id
    assert provenance.snapshot_id == snapshot_id
    assert provenance.run_id == run_id
    assert provenance.query_id == query_id
    assert provenance.provider_attempt_id == provider_attempt_id

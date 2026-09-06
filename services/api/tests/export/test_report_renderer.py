from __future__ import annotations

from clearcut.export.application.report_pipeline import (
    LEGAL_BOUNDARY,
    canonical_json,
    content_hash,
    payload_hash,
    render_html,
)


def _payload() -> dict[str, object]:
    return {
        "schemaVersion": "clearcut-report-v1",
        "generatorVersion": "clearcut-deterministic-html-v1",
        "project": {"projectId": "project-1", "title": "<script>unsafe()</script>"},
        "scriptVersion": {
            "versionId": "version-1",
            "scriptId": "script-1",
            "scriptTitle": "Example",
            "ordinal": 1,
            "sourceHash": "a" * 64,
            "parserVersion": "parser-1",
            "createdAt": "2026-09-06T00:00:00+00:00",
        },
        "items": [
            {
                "itemId": "item-1",
                "category": "products_and_trademarks",
                "entityName": "Example item",
                "status": "open",
                "workflowStatus": "review",
                "researchStatus": "completed",
                "dispositionStatus": "pending",
                "claimCount": 1,
                "evidenceState": "cited",
                "claims": [
                    {
                        "claimId": "claim-1",
                        "stance": "supports",
                        "authorityTier": "secondary",
                        "claimText": "Attributable context.",
                        "provenanceExcerpt": "Quoted context.",
                        "source": {
                            "snapshotId": "source-1",
                            "url": "javascript:alert(1)",
                            "title": "Unsafe source URL",
                            "publisher": "Example publisher",
                            "excerpt": "Quoted context.",
                            "origin": "e2e-fixture-not-a-provider-receipt",
                            "sha256Hash": "b" * 64,
                            "retrievedAt": "2026-09-06T00:00:00+00:00",
                        },
                    }
                ],
                "conflicts": [],
                "decisions": [],
            }
        ],
        "openItemCount": 1,
        "monitoring": {"watchCount": 0},
        "evaluation": {"status": "unavailable"},
        "policyBinding": {"status": "unavailable"},
        "legalBoundary": LEGAL_BOUNDARY,
    }


def test_report_hash_and_html_are_deterministic_and_block_active_source_urls() -> None:
    payload = _payload()
    reordered = dict(reversed(list(payload.items())))

    assert canonical_json(payload) == canonical_json(reordered)
    assert payload_hash(payload) == payload_hash(reordered)

    manifest_hash = payload_hash(payload)
    first = render_html(payload, manifest_hash)
    second = render_html(payload, manifest_hash)
    assert first == second
    assert content_hash(first) == content_hash(second)
    assert "<script>unsafe()</script>" not in first
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in first
    assert 'href="javascript:' not in first
    assert 'href="#"' in first
    assert "javascript:alert(1)" in first

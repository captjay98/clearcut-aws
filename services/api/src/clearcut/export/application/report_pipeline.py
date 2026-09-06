"""Canonical report payload hashing and deterministic local HTML rendering."""

from __future__ import annotations

import hashlib
import html
import json
from typing import Any
from urllib.parse import urlsplit

LEGAL_BOUNDARY = (
    "ClearCut provides sourced findings for qualified human review. "
    "It does not provide legal advice or final legal clearance."
)
REPORT_SCHEMA_VERSION = "clearcut-report-v1"
REPORT_GENERATOR_VERSION = "clearcut-deterministic-html-v1"


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _safe_href(value: object) -> str:
    raw_url = str(value).strip()
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "#"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "#"
    return _escape(raw_url)


def render_html(payload: dict[str, Any], manifest_hash: str) -> str:
    project = payload["project"]
    version = payload["scriptVersion"]
    item_sections: list[str] = []

    for item in payload["items"]:
        claim_sections: list[str] = []
        for claim in item["claims"]:
            source = claim["source"]
            claim_sections.append(
                '<article class="claim exhibit">'
                f"<h3>{_escape(source['title'])}</h3>"
                f'<p><a href="{_safe_href(source["url"])}">{_escape(source["url"])}</a></p>'
                f"<p>Publisher: {_escape(source['publisher'])} · "
                f"Authority: {_escape(claim['authorityTier'])} · "
                f"Stance: {_escape(claim['stance'])}</p>"
                f"<blockquote>{_escape(claim['provenanceExcerpt'])}</blockquote>"
                f"<p>{_escape(claim['claimText'])}</p>"
                "</article>"
            )

        if not claim_sections:
            claim_sections.append(
                '<p class="unresolved">Zero cited evidence remains unresolved. '
                "No fallback evidence has been invented.</p>"
            )

        conflict_sections = "".join(
            f"<li>{_escape(conflict['description'])}</li>" for conflict in item["conflicts"]
        )
        decision_sections = "".join(
            f"<li>{_escape(decision['decision'])}: {_escape(decision['rationale'])}</li>"
            for decision in item["decisions"]
        )
        item_sections.append(
            '<section class="item exhibit">'
            f"<h2>{_escape(item['entityName'])}</h2>"
            f"<p>Category: {_escape(item['category'])} · "
            f"Workflow: {_escape(item['workflowStatus'])} · "
            f"Research: {_escape(item['researchStatus'])} · "
            f"Disposition: {_escape(item['dispositionStatus'])}</p>"
            f"{''.join(claim_sections)}"
            f"<h3>Conflicts ({len(item['conflicts'])})</h3><ul>{conflict_sections}</ul>"
            f"<h3>Human decisions ({len(item['decisions'])})</h3><ul>{decision_sections}</ul>"
            "</section>"
        )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>ClearCut Clearance Report</title>\n"
        "<style>"
        "body{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;"
        "color:#0f172a;line-height:1.5}"
        "header,.exhibit,.legal-boundary{break-inside:avoid;padding:16px;"
        "border:1px solid #cbd5e1;margin:0 0 16px}"
        ".hash{font-family:monospace;overflow-wrap:anywhere}"
        ".unresolved{color:#92400e;font-weight:700}"
        "blockquote{border-left:3px solid #d97706;margin-left:0;padding-left:12px}"
        "@media print{body{margin:0;max-width:none}.no-print{display:none}}"
        "</style>\n</head>\n<body>\n"
        "<header>"
        "<h1>ClearCut Clearance Report</h1>"
        f"<p>Project: {_escape(project['title'])}</p>"
        f"<p>Script: {_escape(version['scriptTitle'])} · Version {_escape(version['ordinal'])}</p>"
        f'<p class="hash">Binding manifest SHA-256: {_escape(manifest_hash)}</p>'
        f"<p>Open items: {_escape(payload['openItemCount'])}</p>"
        "</header>"
        f"{''.join(item_sections)}"
        '<section class="exhibit"><h2>Monitoring and trust bindings</h2>'
        f"<p>Monitoring watches: {_escape(payload['monitoring']['watchCount'])}</p>"
        f"<p>Evaluation status: {_escape(payload['evaluation']['status'])}</p>"
        f"<p>Policy binding: {_escape(payload['policyBinding']['status'])}</p>"
        "</section>"
        '<section class="legal-boundary"><h2>Legal boundary</h2>'
        f"<p>{_escape(payload['legalBoundary'])}</p></section>"
        "\n</body>\n</html>\n"
    )

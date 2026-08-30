import uuid6
from clearcut.export.adapters.html_pdf_renderer import DeterministicReportRenderer
from clearcut.export.domain.snapshots import ReportSnapshot, ReportSnapshotStatus


def test_render_html_is_deterministic_and_contains_legal_boundary():
    renderer = DeterministicReportRenderer()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()

    snapshot = ReportSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        script_version_id=uuid6.uuid7(),
        status=ReportSnapshotStatus.RELEASED,
        content_hash="sha256:fixedhash",
        binding_manifest={"version_ordinal": 1, "item_count": 38},
    )

    html1 = renderer.render_html(snapshot)
    html2 = renderer.render_html(snapshot)

    assert html1 == html2
    assert "Pre-Clearance Evidence Dossier" in html1
    assert "Does not constitute legal advice" in html1

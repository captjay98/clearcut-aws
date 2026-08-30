from clearcut.export.domain.snapshots import ReportSnapshot


class DeterministicReportRenderer:
    def render_html(self, snapshot: ReportSnapshot) -> str:
        manifest = snapshot.binding_manifest
        v_ord = manifest.get("version_ordinal", 1)
        item_count = manifest.get("item_count", 0)

        legal_notice = (
            "ClearCut provides structured research and workflow coordination for human "
            "clearance review. Does not constitute legal advice or formal clearance guarantee."
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ClearCut Pre-Clearance Dossier</title>
  <style>
    body {{ font-family: sans-serif; margin: 40px; color: #0f172a; line-height: 1.5; }}
    .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; }}
    .legal {{ margin-top: 40px; padding: 16px; background: #f8fafc; border: 1px solid #e2e8f0; }}
    .hash {{ font-family: monospace; font-size: 11px; color: #64748b; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Pre-Clearance Evidence Dossier</h1>
    <p>Version Ordinal: v{v_ord} • Total Items Evaluated: {item_count}</p>
    <p class="hash">Snapshot Content Hash: {snapshot.content_hash}</p>
  </div>
  <div class="content">
    <h2>Exhibits & Evidence Lineage</h2>
    <p>This report is frozen and version-bound to Script Version {snapshot.script_version_id}.</p>
  </div>
  <div class="legal">
    <strong>Notice & Legal Boundary:</strong> {legal_notice}
  </div>
</body>
</html>"""

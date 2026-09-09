import React from "react";
import { Card } from "../../components/ds";

export interface ReportReceiptViewProps {
  releaseId: string;
  releasedBy: string;
  releasedAt: string;
  manifestHash: string;
  attestation: string;
  downloadUrl: string;
}

export function ReportReceiptView({
  releaseId,
  releasedBy,
  releasedAt,
  manifestHash,
  attestation,
  downloadUrl,
}: ReportReceiptViewProps) {
  return (
    <section
      className="section"
      data-testid="report-receipt-view"
      aria-labelledby="report-receipt-heading"
    >
      <div className="section-head">
        <div>
          <h2 id="report-receipt-heading">Report release receipt</h2>
          <p>Server-persisted projection of the accountable release transaction.</p>
        </div>
        <a className="button button-primary" href={downloadUrl}>
          Download released HTML
        </a>
      </div>

      <Card>
        <dl className="report-meta">
          <div>
            <dt>Release identifier</dt>
            <dd className="mono">
              Release ID: <span data-testid="release-id">{releaseId}</span>
            </dd>
          </div>
          <div>
            <dt>Accountable reviewer</dt>
            <dd className="mono">{releasedBy}</dd>
          </div>
          <div>
            <dt>Released at</dt>
            <dd>{new Date(releasedAt).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Frozen binding</dt>
            <dd className="mono">Binding manifest SHA-256: {manifestHash}</dd>
          </div>
        </dl>

        <div className="source-card gap-t-5">
          <span className="field-label">Release attestation</span>
          <p className="small gap-t-2">{attestation}</p>
        </div>

        <p className="small muted gap-t-4">
          ClearCut provides sourced findings for qualified human review. It does not provide legal
          advice or final legal clearance.
        </p>
      </Card>
    </section>
  );
}

export default ReportReceiptView;

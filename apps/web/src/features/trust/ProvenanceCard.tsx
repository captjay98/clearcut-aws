import React from "react";
import type { EvaluationProvenance } from "@clearcut/contracts";
import { Card } from "../../components/ds";

export interface ProvenanceCardProps {
  provenance: EvaluationProvenance;
}

/**
 * The exact versions this run was graded against — the binding a released report
 * carries too.
 *
 * Optional fields are omitted rather than shown as zero or "unknown": an absent
 * latency is not a fast one, and an absent token count is not a free call. The
 * requested and returned models are shown separately, because a substituted
 * model is a fact about the evaluation, not a detail to smooth over.
 */
export function ProvenanceCard({ provenance }: ProvenanceCardProps) {
  const substituted =
    provenance.requestedModel &&
    provenance.returnedModel &&
    provenance.requestedModel !== provenance.returnedModel;

  const cost: string[] = [];
  if (provenance.latencyMs !== null && provenance.latencyMs !== undefined) {
    cost.push(`${provenance.latencyMs} ms`);
  }
  if (provenance.totalTokens !== null && provenance.totalTokens !== undefined) {
    cost.push(`${provenance.totalTokens} tokens`);
  }
  if (provenance.repairCount !== undefined) {
    cost.push(
      `${provenance.repairCount} repair${provenance.repairCount === 1 ? "" : "s"}`,
    );
  }

  return (
    <Card eyebrow="For the record" testId="trust-provenance">
      <div className="stack-sm">
        <p className="mono small">
          rubric {provenance.rubricVersion}
          <br />
          prompt {provenance.promptVersion}
          <br />
          policy {provenance.policyVersion}
          {provenance.requestedModel && (
            <>
              <br />
              judge requested {provenance.requestedModel}
            </>
          )}
          {provenance.returnedModel && (
            <>
              <br />
              judge returned {provenance.returnedModel}
            </>
          )}
          {cost.length > 0 && (
            <>
              <br />
              {cost.join(" · ")}
            </>
          )}
        </p>
        {provenance.inputSha256 && (
          <p className="mono small muted truncate">input {provenance.inputSha256}</p>
        )}
        <p className="small muted">
          The exact versions this check was graded against. A released report
          carries the same ones.
        </p>
        {substituted && (
          <p className="small">
            The judge model that answered is not the one requested, so this score
            was produced under a substituted model.
          </p>
        )}
      </div>
    </Card>
  );
}

export default ProvenanceCard;

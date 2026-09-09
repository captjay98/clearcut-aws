import React, { useState } from "react";
import { api, type RewriteProposal } from "@clearcut/contracts";
import { Badge, Banner, Card } from "../../components/ds";
import { humanizeStatus } from "../clearance/itemPresentation";
import type { Tone } from "../../components/ds";

export interface RewriteProposalCardProps {
  orgSlug: string;
  projectId: string;
  itemId: string;
  /** The passage the proposal replaces, shown as the "before" side. */
  originalText: string;
}

function statusTone(status: string): Tone {
  if (status === "approved") {
    return "is-success";
  }
  if (status === "rejected" || status === "withdrawn") {
    return "is-danger";
  }
  return "is-warning";
}

/**
 * Propose replacement text for a flagged passage, and approve or reject a
 * proposal. Each action is a governed API call that records an audit event; a
 * rewrite is never applied locally.
 *
 * This card previously seeded a fabricated proposal into local state and let
 * Approve mutate only that state, so a reviewer could appear to approve a
 * rewrite that never existed and was never recorded. Nothing here is invented
 * now, and every button hits the real endpoint.
 *
 * Scope limit worth stating: ClearanceItemDetail carries no rewriteProposals
 * field and there is no list endpoint, so this shows the proposals raised in
 * this session rather than a persisted history.
 */
export function RewriteProposalCard({
  orgSlug,
  projectId,
  itemId,
  originalText,
}: RewriteProposalCardProps) {
  const [proposals, setProposals] = useState<RewriteProposal[]>([]);
  const [proposedText, setProposedText] = useState("");
  const [rationale, setRationale] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePropose = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = proposedText.trim();
    if (!text) return;

    setPending(true);
    setError(null);
    try {
      const result = await api.proposeRewrite({
        params: { orgId: orgSlug, projectId, itemId },
        body: { proposedText: text, rationale: rationale.trim() || undefined },
      });
      if (!result.ok) {
        setError(result.error.message || "The rewrite proposal was not recorded.");
        return;
      }
      setProposals((current) => [...current, result.value]);
      setProposedText("");
      setRationale("");
    } catch {
      setError("A network error prevented the rewrite proposal from being recorded.");
    } finally {
      setPending(false);
    }
  };

  const decide = async (proposalId: string, decision: "approve" | "reject") => {
    setPending(true);
    setError(null);
    try {
      const call = decision === "approve" ? api.approveRewrite : api.rejectRewrite;
      const result = await call({ params: { orgId: orgSlug, projectId, proposalId } });
      if (!result.ok) {
        setError(result.error.message || `The rewrite could not be ${decision}d.`);
        return;
      }
      setProposals((current) =>
        current.map((proposal) =>
          proposal.proposalId === proposalId ? result.value : proposal,
        ),
      );
    } catch {
      setError(`A network error prevented the ${decision} from being recorded.`);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="section" data-testid="rewrite-proposals-section">
      <div className="section-head">
        <div>
          <h2>Rewrite proposals</h2>
          <p>
            An approved rewrite creates the next immutable version and re-checks only the passages
            it changed. The proposer cannot approve their own rewrite.
          </p>
        </div>
      </div>

      {error && (
        <Banner
          tone="is-danger"
          icon="⚠"
          title="Action not recorded"
          message={error}
          role="alert"
          className="gap-b-4"
        />
      )}

      {proposals.length > 0 && (
        <div className="stack gap-b-4">
          {proposals.map((proposal) => (
            <Card key={proposal.proposalId}>
              <div className="diff">
                <section>
                  <span className="field-label">Original passage</span>
                  <p className="diff-text">
                    <del>{originalText}</del>
                  </p>
                </section>
                <section>
                  <span className="field-label">Proposed replacement</span>
                  <p className="diff-text">
                    <ins>{proposal.proposedText}</ins>
                  </p>
                </section>
              </div>

              {proposal.rationale && <p className="small gap-t-3">{proposal.rationale}</p>}

              <div className="cluster-between gap-t-4">
                <Badge tone={statusTone(proposal.status)}>{humanizeStatus(proposal.status)}</Badge>
                {proposal.status === "proposed" && (
                  <div className="cluster">
                    <button
                      className="button button-secondary button-sm"
                      type="button"
                      disabled={pending}
                      onClick={() => void decide(proposal.proposalId, "reject")}
                    >
                      Reject
                    </button>
                    <button
                      className="button button-primary button-sm"
                      type="button"
                      disabled={pending}
                      onClick={() => void decide(proposal.proposalId, "approve")}
                    >
                      Approve Rewrite
                    </button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <form onSubmit={handlePropose}>
          <div className="form-grid">
            <div className="field field-full">
              <label className="field-label" htmlFor="proposed-text">
                Proposed replacement text
              </label>
              <input
                id="proposed-text"
                type="text"
                required
                value={proposedText}
                onChange={(event) => setProposedText(event.target.value)}
                placeholder="Replacement wording for the flagged passage"
              />
            </div>
            <div className="field field-full">
              <label className="field-label" htmlFor="rewrite-rationale">
                Rationale
              </label>
              <input
                id="rewrite-rationale"
                type="text"
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                placeholder="Why this replacement resolves the concern"
              />
            </div>
          </div>
          <div className="cluster gap-t-4" style={{ justifyContent: "flex-end" }}>
            <button
              className="button button-primary"
              type="submit"
              disabled={pending || !proposedText.trim()}
            >
              {pending ? "Submitting…" : "Submit Proposal"}
            </button>
          </div>
        </form>
      </Card>
    </section>
  );
}

export default RewriteProposalCard;

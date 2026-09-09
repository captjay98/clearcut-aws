import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ApiError, ItemCapability, RewriteProposal } from "@clearcut/contracts";
import { Badge, Banner, Card, EmptyState } from "../../components/ds";
import { humanizeStatus } from "../clearance/itemPresentation";
import type { Tone } from "../../components/ds";
import {
  rewriteProposalsQueryOptions,
  rewriteViewerQueryOptions,
} from "../../queries/rewriteProposals";
import {
  proposeRewriteMutationOptions,
  rewriteTransitionMutationOptions,
  type RewriteTransition,
} from "../../mutations/rewriteProposalCommands";

export interface RewriteProposalCardProps {
  orgSlug: string;
  projectId: string;
  itemId: string;
  /**
   * The passage the item was detected in, used only as a fallback. Each
   * persisted proposal carries the original text the server recorded against
   * it, which is what a reviewer must read.
   */
  originalText: string;
  /** Server-derived `rewrite:propose` capability for this item and role. */
  proposeCapability?: ItemCapability;
  /** Server-derived `rewrite:approve` capability for this item and role. */
  approveCapability?: ItemCapability;
}

interface ActionFailure {
  message: string;
  code?: ApiError["code"];
}

function statusTone(status: string): Tone {
  if (status === "approved" || status === "materialized") {
    return "is-success";
  }
  if (status === "rejected" || status === "withdrawn") {
    return "is-danger";
  }
  return "is-warning";
}

function formatTimestamp(value: string | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleString();
}

function toActionFailure(error: unknown, fallback: string): ActionFailure {
  const apiError = error as (Error & Partial<ApiError>) | undefined;
  return {
    message: apiError?.message || fallback,
    ...(apiError?.code ? { code: apiError.code } : {}),
  };
}

/**
 * The governed rewrite-proposal history for one clearance item, plus the form
 * that raises a new one.
 *
 * The history used to live in `useState`, which meant a proposal vanished on
 * reload and was never visible to the second person who has to decide on it --
 * so the maker-checker feature could not actually be exercised by two people.
 * It is now read from `listRewriteProposals`, and every action refetches that
 * read rather than patching a local array, so what is on screen is what is
 * persisted.
 *
 * What approval does and does not do is stated honestly here: it records an
 * accountable decision, it does not create a successor script version, and it
 * does not start research. `resultingVersionId` stays absent until a separate
 * materialization step binds one, and re-checking affected passages is the
 * separate explicit selective-rescan action on the versions surface.
 *
 * Button visibility follows capability and maker-checker as a convenience only.
 * The server authorizes every call regardless, and refuses self-approval even
 * for an owner.
 */
export function RewriteProposalCard({
  orgSlug,
  projectId,
  itemId,
  originalText,
  proposeCapability,
  approveCapability,
}: RewriteProposalCardProps) {
  const queryClient = useQueryClient();
  const scope = { orgId: orgSlug, projectId, itemId };
  const proposalsQuery = useQuery(rewriteProposalsQueryOptions(scope));
  const viewerQuery = useQuery(rewriteViewerQueryOptions());
  const proposeMutation = useMutation(proposeRewriteMutationOptions(scope, queryClient));
  const transitionMutation = useMutation(
    rewriteTransitionMutationOptions(scope, queryClient),
  );

  const [proposedText, setProposedText] = useState("");
  const [rationale, setRationale] = useState("");
  const [failure, setFailure] = useState<ActionFailure | null>(null);

  const viewerId = viewerQuery.data ?? null;
  const proposals = proposalsQuery.data ?? [];
  const proposeAllowed = proposeCapability?.allowed ?? false;
  const approveAllowed = approveCapability?.allowed ?? false;
  const busy = proposeMutation.isPending || transitionMutation.isPending;

  const isOwnProposal = (proposal: RewriteProposal): boolean =>
    viewerId !== null && proposal.proposerId === viewerId;

  /**
   * Maker-checker as a UI convenience. When the viewer identity or the
   * proposer identity cannot be established locally, the decision buttons are
   * withheld rather than guessed; the server is the control either way.
   */
  const mayDecide = (proposal: RewriteProposal): boolean => {
    if (!approveAllowed || proposal.status !== "proposed") return false;
    if (viewerId === null || !proposal.proposerId) return false;
    return proposal.proposerId !== viewerId;
  };

  const mayWithdraw = (proposal: RewriteProposal): boolean =>
    proposal.status === "proposed" && proposeAllowed && isOwnProposal(proposal);

  const handlePropose = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = proposedText.trim();
    if (!text || busy) return;

    const submittedRationale = rationale.trim();
    // Cleared before the await so a resolved write cannot leave the draft on
    // screen next to the persisted proposal; restored verbatim below if the
    // server does not confirm, because losing a typed rewrite is unacceptable.
    setProposedText("");
    setRationale("");
    setFailure(null);
    try {
      await proposeMutation.mutateAsync({
        proposedText: text,
        ...(submittedRationale ? { rationale: submittedRationale } : {}),
      });
    } catch (error) {
      setProposedText(text);
      setRationale(submittedRationale);
      const failed = toActionFailure(
        error,
        "The rewrite service did not confirm the proposal.",
      );
      setFailure({
        ...failed,
        message: `The rewrite proposal was not recorded: ${failed.message} Your text is preserved.`,
      });
    }
  };

  const handleTransition = async (
    proposalId: string,
    transition: RewriteTransition,
  ) => {
    if (busy) return;
    setFailure(null);
    try {
      await transitionMutation.mutateAsync({ proposalId, transition });
    } catch (error) {
      setFailure(
        toActionFailure(error, `The ${transition} was not recorded by the server.`),
      );
    }
  };

  const staleConflict = failure?.code === "conflict_stale_version";

  return (
    <section className="section" data-testid="rewrite-proposals-section">
      <div className="section-head">
        <div>
          <h2>Rewrite proposals</h2>
          <p>
            Every action here is a governed call recorded as an audit event. Approval records an
            accountable decision only: it creates no script version and starts no research.
            Materializing an approved rewrite and re-checking the passages it changes is a separate
            explicit step on the versions surface. The proposer cannot approve their own rewrite.
          </p>
        </div>
      </div>

      {failure && (
        <Banner
          tone="is-danger"
          icon="⚠"
          title={staleConflict ? "Rewrite is out of date" : "Action not recorded"}
          message={
            staleConflict
              ? `${failure.message} Nothing was retried automatically.`
              : failure.message
          }
          role="alert"
          titleIsHeading
          className="gap-b-4"
        />
      )}

      {proposalsQuery.isPending ? (
        <p role="status" className="small muted gap-b-4">
          Loading rewrite proposals…
        </p>
      ) : proposalsQuery.isError ? (
        <Banner
          tone="is-danger"
          icon="⚠"
          title="Rewrite history unavailable"
          message={`${
            proposalsQuery.error?.message ??
            "The rewrite proposal history could not be loaded."
          } No proposals are shown rather than an incomplete history.`}
          role="alert"
          titleIsHeading
          className="gap-b-4"
        />
      ) : proposals.length === 0 ? (
        <div className="gap-b-4">
          <EmptyState
            icon="✎"
            title="No rewrite proposals recorded"
            description="Proposals raised here persist for every authorized reviewer on this item."
          />
        </div>
      ) : (
        <ol
          className="stack gap-b-4"
          aria-label="Rewrite proposal history"
          style={{ listStyle: "none", padding: 0 }}
        >
          {proposals.map((proposal) => {
            const created = formatTimestamp(proposal.createdAt);
            const updated = formatTimestamp(proposal.updatedAt);
            return (
              <li key={proposal.proposalId}>
                <Card testId="rewrite-proposal">
                  <div className="cluster-between">
                    <span className="small">
                      Proposed by {proposal.proposerEmail ?? proposal.proposerId ?? "an authorized member"}
                    </span>
                    <Badge tone={statusTone(proposal.status)}>
                      {humanizeStatus(proposal.status)}
                    </Badge>
                  </div>

                  <div className="diff gap-t-3">
                    <section>
                      <span className="field-label">Original passage</span>
                      <p className="diff-text">
                        <del>{proposal.originalText ?? originalText}</del>
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
                  {proposal.rejectionReason && (
                    <p className="small gap-t-2">Rejection reason: {proposal.rejectionReason}</p>
                  )}

                  <div className="cluster gap-t-2">
                    {created && (
                      <span className="mono small muted">Raised {created}</span>
                    )}
                    {updated && updated !== created && (
                      <span className="mono small muted">Last change {updated}</span>
                    )}
                  </div>

                  {proposal.resultingVersionId ? (
                    <p className="small gap-t-2">
                      <Link
                        to="/o/$orgSlug/projects/$projectId/versions"
                        params={{ orgSlug, projectId }}
                        search={{ versionId: proposal.resultingVersionId }}
                      >
                        Open the resulting script version →
                      </Link>
                    </p>
                  ) : (
                    proposal.status === "approved" && (
                      <p className="small muted gap-t-2">
                        No successor version is bound to this approval. Approval creates none;
                        materializing it is a separate step.
                      </p>
                    )
                  )}

                  {proposal.status === "proposed" && isOwnProposal(proposal) && (
                    <p className="small muted gap-t-2">
                      You raised this rewrite, so a different accountable reviewer has to decide on
                      it.
                    </p>
                  )}

                  {(mayDecide(proposal) || mayWithdraw(proposal)) && (
                    <div className="cluster gap-t-4" style={{ justifyContent: "flex-end" }}>
                      {mayWithdraw(proposal) && (
                        <button
                          className="button button-quiet button-sm"
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            void handleTransition(proposal.proposalId, "withdraw")
                          }
                        >
                          Withdraw Proposal
                        </button>
                      )}
                      {mayDecide(proposal) && (
                        <>
                          <button
                            className="button button-secondary button-sm"
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void handleTransition(proposal.proposalId, "reject")
                            }
                          >
                            Reject
                          </button>
                          <button
                            className="button button-primary button-sm"
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void handleTransition(proposal.proposalId, "approve")
                            }
                          >
                            Approve Rewrite
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ol>
      )}

      <Card>
        {/* The server's own explanation of why proposing is or is not permitted.
            Focusable so a denial can be read without a mouse. */}
        <p className="small muted" tabIndex={0}>
          {proposeCapability?.explanation ??
            "Rewrite proposal capability is unavailable for this item and current role."}
        </p>

        <form onSubmit={handlePropose} className="gap-t-4">
          <fieldset disabled={!proposeAllowed || busy}>
            <legend className="sr-only">Propose a replacement passage</legend>
            <div className="form-grid">
              <div className="field field-full">
                <label className="field-label" htmlFor="proposed-text">
                  Proposed replacement text
                </label>
                <textarea
                  id="proposed-text"
                  rows={2}
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
                <textarea
                  id="rewrite-rationale"
                  rows={2}
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
                disabled={!proposedText.trim()}
              >
                {proposeMutation.isPending ? "Submitting…" : "Submit Proposal"}
              </button>
            </div>
          </fieldset>
        </form>
      </Card>
    </section>
  );
}

export default RewriteProposalCard;

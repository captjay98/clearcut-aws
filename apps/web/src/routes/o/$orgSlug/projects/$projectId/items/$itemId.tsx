import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import type {
  ApiError,
  ClearanceDisposition,
  EvidenceDecision,
} from "@clearcut/contracts";
import { ItemGovernanceControls } from "../../../../../../features/clearance/ItemGovernanceControls";
import { CommentThread } from "../../../../../../features/collaboration/CommentThread";
import { ReferralCard } from "../../../../../../features/collaboration/ReferralCard";
import { RewriteProposalCard } from "../../../../../../features/collaboration/RewriteProposalCard";
import {
  acknowledgeReferralMutationOptions,
  addCommentMutationOptions,
  assignClearanceItemMutationOptions,
  recordEvidenceDecisionMutationOptions,
  referClearanceItemMutationOptions,
  replyToCommentMutationOptions,
  reviseCommentMutationOptions,
  setDispositionMutationOptions,
} from "../../../../../../mutations/clearanceItemCommands";
import { clearanceItemDetailQueryOptions } from "../../../../../../queries/clearanceItems";
import { organizationMentionRecipientsQueryOptions } from "../../../../../../queries/organizationMembers";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/items/$itemId")({
  component: ItemDetailRoute,
});

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export function ItemDetailRoute() {
  const { orgSlug, projectId, itemId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/items/$itemId",
  });
  const queryClient = useQueryClient();
  const scope = { orgId: orgSlug, projectId, itemId };
  const itemQuery = useQuery(clearanceItemDetailQueryOptions(scope));
  const mentionRecipientsQuery = useQuery(
    organizationMentionRecipientsQueryOptions({ orgId: orgSlug, projectId }),
  );
  const decisionMutation = useMutation(
    recordEvidenceDecisionMutationOptions(scope, queryClient),
  );
  const commentMutation = useMutation(addCommentMutationOptions(scope, queryClient));
  const referralMutation = useMutation(
    referClearanceItemMutationOptions(scope, queryClient),
  );
  const acknowledgementMutation = useMutation(
    acknowledgeReferralMutationOptions(scope, queryClient),
  );
  const replyMutation = useMutation(replyToCommentMutationOptions(scope, queryClient));
  const revisionMutation = useMutation(reviseCommentMutationOptions(scope, queryClient));
  const assignmentMutation = useMutation(
    assignClearanceItemMutationOptions(scope, queryClient),
  );
  const dispositionMutation = useMutation(
    setDispositionMutationOptions(scope, queryClient),
  );
  const [decision, setDecision] = useState<EvidenceDecision>("further_review_required");
  const [rationale, setRationale] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  const item = itemQuery.data;
  const decisionCapability = item?.capabilities.find(
    (capability) => capability.action === "item:decide",
  );
  const assignmentCapability = item?.capabilities.find(
    (capability) => capability.action === "item:assign",
  );
  const dispositionCapability = item?.capabilities.find(
    (capability) => capability.action === "item:disposition",
  );
  const referralCapability = item?.capabilities.find(
    (capability) => capability.action === "item:refer",
  );

  const handleAssign = async (assigneeId: string | null) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "assignClearanceItem",
        orgId: orgSlug,
        projectId,
        itemId,
        assigneeId,
        expectedVersion: item.version,
      }),
    );
    await assignmentMutation.mutateAsync({
      assigneeId,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `assignment-${crypto.randomUUID()}`,
    });
  };

  const handleSetDisposition = async (
    disposition: ClearanceDisposition,
    dispositionRationale: string,
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "setDisposition",
        orgId: orgSlug,
        projectId,
        itemId,
        disposition,
        rationale: dispositionRationale,
        expectedVersion: item.version,
      }),
    );
    await dispositionMutation.mutateAsync({
      disposition,
      rationale: dispositionRationale,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `disposition-${crypto.randomUUID()}`,
    });
  };

  const handleRecordDecision = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!item || !rationale.trim() || !decisionCapability?.allowed) return;
    setFeedback(null);

    const trimmedRationale = rationale.trim();
    try {
      const intentHash = await sha256(
        JSON.stringify({
          operation: "recordEvidenceDecision",
          orgId: orgSlug,
          projectId,
          itemId,
          decision,
          rationale: trimmedRationale,
          expectedVersion: item.version,
        }),
      );
      await decisionMutation.mutateAsync({
        decision,
        rationale: trimmedRationale,
        expectedVersion: item.version,
        intentHash,
        idempotencyKey: `decision-${crypto.randomUUID()}`,
      });
      setRationale("");
      setFeedback("Evidence-review decision recorded. The item remains subject to human review.");
    } catch (error) {
      const apiError = error as Error & Partial<ApiError>;
      setFeedback(
        apiError.code === "conflict_stale_version"
          ? "This item changed during review. Your rationale is preserved; review the refreshed state and submit again."
          : `Decision not recorded: ${apiError.message || "The clearance service is unavailable."}`,
      );
    }
  };

  const handleAddComment = async (
    content: string,
    mentionRecipientIds: string[],
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "addComment",
        orgId: orgSlug,
        projectId,
        itemId,
        body: content,
        mentions: mentionRecipientIds,
        expectedVersion: item.version,
      }),
    );
    await commentMutation.mutateAsync({
      body: content,
      mentions: mentionRecipientIds,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `comment-${crypto.randomUUID()}`,
    });
  };

  const handleReplyToComment = async (
    commentId: string,
    content: string,
    mentionRecipientIds: string[],
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "replyToComment",
        orgId: orgSlug,
        projectId,
        itemId,
        commentId,
        body: content,
        mentions: mentionRecipientIds,
        expectedVersion: item.version,
      }),
    );
    await replyMutation.mutateAsync({
      commentId,
      body: content,
      mentions: mentionRecipientIds,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `comment-reply-${crypto.randomUUID()}`,
    });
  };

  const handleReviseComment = async (
    commentId: string,
    content: string,
    mentionRecipientIds: string[],
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "reviseComment",
        orgId: orgSlug,
        projectId,
        itemId,
        commentId,
        body: content,
        mentions: mentionRecipientIds,
        expectedVersion: item.version,
      }),
    );
    await revisionMutation.mutateAsync({
      commentId,
      body: content,
      mentions: mentionRecipientIds,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `comment-revision-${crypto.randomUUID()}`,
    });
  };

  const handleRefer = async (
    targetRole: string,
    question: string,
    referralRationale: string,
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "referClearanceItem",
        orgId: orgSlug,
        projectId,
        itemId,
        targetRole,
        question,
        rationale: referralRationale,
        expectedVersion: item.version,
      }),
    );
    await referralMutation.mutateAsync({
      targetRole,
      question,
      rationale: referralRationale,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `referral-${crypto.randomUUID()}`,
    });
  };

  const handleAcknowledgeReferral = async (
    referralId: string,
    response: string,
    acknowledgementRationale: string,
  ) => {
    if (!item) throw new Error("The clearance item is unavailable.");
    const intentHash = await sha256(
      JSON.stringify({
        operation: "acknowledgeReferral",
        orgId: orgSlug,
        projectId,
        itemId,
        referralId,
        response,
        rationale: acknowledgementRationale,
        expectedVersion: item.version,
      }),
    );
    await acknowledgementMutation.mutateAsync({
      referralId,
      response,
      rationale: acknowledgementRationale,
      expectedVersion: item.version,
      intentHash,
      idempotencyKey: `referral-acknowledgement-${crypto.randomUUID()}`,
    });
  };

  if (itemQuery.isPending) {
    return <div className="p-6 text-xs text-slate-400 font-sans">Loading clearance item…</div>;
  }

  if (itemQuery.isError || !item) {
    return (
      <div className="p-6 max-w-2xl font-sans space-y-3">
        <Link
          to="/o/$orgSlug/projects/$projectId/workspace"
          params={{ orgSlug, projectId }}
          className="text-xs text-amber-500 hover:underline inline-block"
        >
          ← Back to Screenplay Workspace
        </Link>
        <div
          role="alert"
          className="p-4 rounded bg-red-950/50 border border-red-900 text-red-400 text-xs"
        >
          {itemQuery.error?.message || "This clearance item is not available."}
        </div>
      </div>
    );
  }

  const snapshots = new Map(item.snapshots.map((snapshot) => [snapshot.snapshotId, snapshot]));

  return (
    <div className="space-y-6 max-w-4xl font-sans">
      <header>
        <Link
          to="/o/$orgSlug/projects/$projectId/workspace"
          params={{ orgSlug, projectId }}
          className="text-xs text-amber-500 hover:underline mb-1 inline-block"
        >
          ← Back to Screenplay Workspace
        </Link>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-3">
          <span>{item.entityName}</span>
          <span className="text-xs px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-normal">
            {item.category}
          </span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          {item.scene !== undefined ? `Scene ${item.scene} • ` : ""}
          {item.page !== undefined ? `Page ${item.page} • ` : ""}
          Status: <span className="font-bold text-amber-400 uppercase">{item.status}</span>
        </p>
      </header>

      <p
        role="note"
        className="rounded border border-slate-800 bg-slate-900 px-4 py-3 text-xs text-slate-300"
      >
        ClearCut provides sourced findings for qualified human review. It does not provide
        legal advice or final legal clearance.
      </p>

      <section className="space-y-3" aria-labelledby="evidence-heading">
        <div>
          <h2 id="evidence-heading" className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Source Snapshots & Evidence Claims ({item.evidenceState.claimCount})
          </h2>
          <p className="mt-1 text-xs text-slate-400">{item.evidenceState.reason}</p>
        </div>

        {item.claims.length === 0 ? (
          <div className="rounded border border-amber-900 bg-amber-950/30 p-4 text-xs text-amber-200">
            Zero cited evidence remains unresolved. No fallback evidence has been invented.
          </div>
        ) : (
          item.claims.map((claim) => {
            const snapshot = snapshots.get(claim.snapshotId);
            return (
              <article
                key={claim.claimId}
                className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-2"
              >
                {snapshot ? (
                  <a
                    href={snapshot.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-bold text-amber-400 hover:underline"
                  >
                    {snapshot.title} ↗
                  </a>
                ) : (
                  <p className="text-xs text-amber-300">Cited source snapshot unavailable.</p>
                )}
                <p className="text-[10px] text-slate-400">
                  {claim.authorityTier} • {claim.stance}
                  {snapshot ? ` • ${snapshot.publisher}` : ""}
                </p>
                <blockquote className="text-xs text-slate-300 italic border-l-2 border-slate-700 pl-3">
                  “{claim.provenanceExcerpt}”
                </blockquote>
                <p className="text-xs text-slate-300">{claim.claimText}</p>
              </article>
            );
          })
        )}
      </section>

      <ItemGovernanceControls
        assignedTo={item.assignedTo}
        disposition={item.disposition}
        assignmentCapability={assignmentCapability}
        dispositionCapability={dispositionCapability}
        onAssign={handleAssign}
        onSetDisposition={handleSetDisposition}
      />

      <section
        data-testid="decision-action-bar"
        className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 shadow-sm"
      >
        <h2 className="text-sm font-bold text-white">Record Evidence-Review Decision</h2>
        <p tabIndex={0} className="text-xs text-slate-400">
          {decisionCapability?.explanation ??
            "Decision capability is unavailable for this item and current role."}
        </p>
        {feedback && (
          <div
            role="alert"
            className={`p-3 rounded text-xs ${
              feedback.startsWith("Decision not") || feedback.startsWith("This item changed")
                ? "bg-red-950/50 border border-red-900 text-red-400"
                : "bg-emerald-950/50 border border-emerald-900 text-emerald-400"
            }`}
          >
            {feedback}
          </div>
        )}

        <form onSubmit={handleRecordDecision} className="space-y-3">
          <fieldset disabled={!decisionCapability?.allowed || decisionMutation.isPending}>
            <legend className="sr-only">Evidence-review outcome</legend>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                {
                  id: "accepted" as const,
                  label: "Accept cited evidence",
                  description: "Use the cited material in continued human review",
                },
                {
                  id: "rejected" as const,
                  label: "Reject cited evidence",
                  description: "Record why the cited material is not reliable",
                },
                {
                  id: "further_review_required" as const,
                  label: "Further review required",
                  description: "Keep unresolved risk open for qualified review",
                },
              ].map((option) => (
                <label
                  key={option.id}
                  className={`p-3 rounded border cursor-pointer transition-all ${
                    decision === option.id
                      ? "bg-amber-950/30 border-amber-500 text-white"
                      : "bg-slate-800/60 border-slate-700 text-slate-300 hover:border-slate-600"
                  }`}
                >
                  <input
                    type="radio"
                    name="decision"
                    value={option.id}
                    checked={decision === option.id}
                    onChange={() => setDecision(option.id)}
                    className="sr-only"
                  />
                  <span className="block text-xs font-bold">{option.label}</span>
                  <span className="block text-[10px] text-slate-400 mt-0.5">
                    {option.description}
                  </span>
                </label>
              ))}
            </div>

            <label htmlFor="rationale" className="block text-xs font-medium text-slate-300 mt-3">
              Accountable rationale
            </label>
            <textarea
              id="rationale"
              required
              rows={3}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              className="mt-1 w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
            <div className="mt-3 flex justify-end">
              <button
                type="submit"
                disabled={!rationale.trim()}
                className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-xs font-bold text-white rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                {decisionMutation.isPending ? "Recording…" : "Record Review Decision"}
              </button>
            </div>
          </fieldset>
        </form>
      </section>

      {item.decisions.length > 0 && (
        <section className="space-y-2" aria-labelledby="decision-history-heading">
          <h2 id="decision-history-heading" className="text-xs font-bold uppercase text-slate-400">
            Attributable decision history
          </h2>
          {item.decisions.map((record) => (
            <article key={record.recordId} className="rounded border border-slate-800 bg-slate-900 p-3 text-xs">
              <p className="font-bold text-slate-200">
                {record.kind}: {record.value}
              </p>
              <p className="mt-1 text-slate-400">{record.rationale}</p>
              <p className="mt-1 font-mono text-[10px] text-slate-500">
                Actor {record.actorId} • version {record.resultingVersion}
              </p>
            </article>
          ))}
        </section>
      )}

      <RewriteProposalCard originalText={item.contextText ?? item.entityName} />
      <ReferralCard
        itemId={item.itemId}
        referrals={item.referrals}
        referralCapability={referralCapability}
        onRefer={handleRefer}
        onAcknowledge={handleAcknowledgeReferral}
      />
      <CommentThread
        comments={item.comments}
        mentionRecipients={mentionRecipientsQuery.data ?? []}
        onAddComment={handleAddComment}
        onReply={handleReplyToComment}
        onRevise={handleReviseComment}
      />
    </div>
  );
}

export default ItemDetailRoute;

import React, { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { api, type Job } from "@clearcut/contracts";
import type {
  ApiError,
  ClearanceDisposition,
  EvidenceDecision,
} from "@clearcut/contracts";
import { ItemGovernanceControls } from "../../../../../../features/clearance/ItemGovernanceControls";
import { ResearchProgress } from "../../../../../../features/clearance/ResearchProgress";
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
  startResearchMutationOptions,
} from "../../../../../../mutations/clearanceItemCommands";
import { clearanceItemDetailQueryOptions, clearanceItemsQueryOptions } from "../../../../../../queries/clearanceItems";
import { organizationMentionRecipientsQueryOptions, assignableMembersQueryOptions } from "../../../../../../queries/organizationMembers";
import { Badge, Banner, Card, Page, Section } from "../../../../../../components/ds";
import {
  displayCategory,
  displayStatus,
  displayStatusTone,
  severityWord,
} from "../../../../../../features/clearance/itemPresentation";
import { EvidencePanel } from "../../../../../../features/clearance/EvidencePanel";

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
  const itemsQuery = useQuery(clearanceItemsQueryOptions({ orgId: orgSlug, projectId }));
  const mentionRecipientsQuery = useQuery(
    organizationMentionRecipientsQueryOptions({ orgId: orgSlug, projectId }),
  );
  const assignableMembersQuery = useQuery(
    assignableMembersQueryOptions({ orgId: orgSlug, projectId }),
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
  const researchMutation = useMutation({
    ...startResearchMutationOptions(scope, queryClient),
    onSuccess: (job: Job) => {
      setResearchJobId(job.jobId);
    },
  });
  const [decision, setDecision] = useState<EvidenceDecision>("further_review_required");
  const [rationale, setRationale] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [researchJobId, setResearchJobId] = useState<string | null>(null);

  // Reconstruct an in-flight research job after reload so progress stays visible.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await api.listJobs({
        params: { orgId: orgSlug, projectId },
      });
      if (cancelled || !result.ok) return;
      const running = result.value.find(
        (job) =>
          job.jobType === "research" &&
          job.target.type === "clearance_item" &&
          job.target.id === itemId &&
          !["succeeded", "failed", "cancelled", "manual_retry"].includes(job.status),
      );
      if (running) setResearchJobId(running.jobId);
    })();
    return () => {
      cancelled = true;
    };
  }, [orgSlug, projectId, itemId]);

  const item = itemQuery.data;
  const siblings = itemsQuery.data ?? [];
  const siblingIndex = siblings.findIndex((row) => row.itemId === itemId);
  const prevFlag = siblingIndex > 0 ? siblings[siblingIndex - 1]! : null;
  const nextFlag =
    siblingIndex >= 0 && siblingIndex < siblings.length - 1 ? siblings[siblingIndex + 1]! : null;
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
  const rewriteProposeCapability = item?.capabilities.find(
    (capability) => capability.action === "rewrite:propose",
  );
  const rewriteApproveCapability = item?.capabilities.find(
    (capability) => capability.action === "rewrite:approve",
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
    return (
      <div className="page">
        <p role="status" className="small muted">
          Loading clearance item…
        </p>
      </div>
    );
  }

  if (itemQuery.isError || !item) {
    return (
      <div className="page narrow">
        <header className="page-head">
          <Link
            to="/o/$orgSlug/projects/$projectId/workspace"
            params={{ orgSlug, projectId }}
          >
            ← Back to Screenplay Workspace
          </Link>
        </header>
        <Banner
          tone="is-danger"
          icon="⚠"
          title="Clearance item unavailable"
          message={itemQuery.error?.message || "This clearance item is not available."}
          role="alert"
          titleIsHeading
        />
      </div>
    );
  }

  return (
    <Page
      trail={[
        { label: "Flags", to: "/o/$orgSlug/projects/$projectId/items", params: { orgSlug, projectId } },
        { label: item.itemId.slice(-8) },
      ]}
      eyebrow={displayCategory(item.category)}
      title={item.entityName}
      lede={
        <>
          {item.scene !== undefined ? `Scene ${item.scene}` : ""}
          {item.page !== undefined ? `, page ${item.page}` : ""}
          {item.scene !== undefined || item.page !== undefined ? " · " : ""}
          {severityWord(item)} priority
        </>
      }
      actions={
        <>
          <Badge tone={displayStatusTone(item)}>{displayStatus(item)}</Badge>
          {siblings.length > 0 && siblingIndex >= 0 && (
            <span className="cluster small muted" data-testid="flag-pager">
              {prevFlag ? (
                <Link
                  className="button button-quiet button-sm"
                  to="/o/$orgSlug/projects/$projectId/items/$itemId"
                  params={{ orgSlug, projectId, itemId: prevFlag.itemId }}
                  search={{ group: "none", sort: "severity", dir: "desc" }}
                  aria-label={`Previous flag: ${prevFlag.entityName}`}
                >
                  ←
                </Link>
              ) : (
                <span aria-hidden="true">←</span>
              )}
              <span>
                {siblingIndex + 1} of {siblings.length} flags
              </span>
              {nextFlag ? (
                <Link
                  className="button button-quiet button-sm"
                  to="/o/$orgSlug/projects/$projectId/items/$itemId"
                  params={{ orgSlug, projectId, itemId: nextFlag.itemId }}
                  search={{ group: "none", sort: "severity", dir: "desc" }}
                  aria-label={`Next flag: ${nextFlag.entityName}`}
                >
                  →
                </Link>
              ) : (
                <span aria-hidden="true">→</span>
              )}
            </span>
          )}
          <button
            type="button"
            className="button button-quiet"
            onClick={() => window.print()}
          >
            Print this record
          </button>
          <Link
            className="button button-quiet"
            to="/o/$orgSlug/projects/$projectId/items"
            params={{ orgSlug, projectId }}
            search={{ group: "none", sort: "severity", dir: "desc" }}
          >
            Back to items
          </Link>
        </>
      }
      notice={
        <p role="note" className="banner">
          <span className="banner-icon" aria-hidden="true">
            ⚖
          </span>
          <span className="banner-body">
            ClearCut provides sourced findings for qualified human review. It does not provide legal
            advice or final legal clearance.
          </span>
        </p>
      }
    >
      {item.contextText && (
        <Section title="Script context" description="Anchored to a stable span, so the record survives revisions.">
          <article className="source-card">
            <p>{item.contextText}</p>
          </article>
        </Section>
      )}

      <Section title="Evidence" description={item.evidenceState.reason}>
        <ResearchProgress
          orgSlug={orgSlug}
          projectId={projectId}
          jobId={researchJobId}
          entityName={item.entityName}
          onSettled={(job) => {
            if (job.status === "succeeded" || job.status === "failed") {
              setResearchJobId(null);
            }
          }}
        />
        <EvidencePanel
          item={item}
          claims={item.claims}
          snapshots={item.snapshots}
          conflictDescriptions={item.conflicts.map((conflict) => conflict.description)}
          emptyAction={
            <div className="stack">
              {researchMutation.isError && (
                <Banner
                  tone="is-danger"
                  icon="⚠"
                  message={`Research not started: ${
                    (researchMutation.error as Error)?.message ||
                    "The clearance service is unavailable."
                  }`}
                  role="alert"
                />
              )}
              <div className="cluster" style={{ justifyContent: "flex-end" }}>
                <button
                  className="button button-primary"
                  type="button"
                  disabled={researchMutation.isPending || Boolean(researchJobId)}
                  onClick={() => researchMutation.mutate(undefined, {
                    onSuccess: (job: Job) => setResearchJobId(job.jobId),
                  })}
                >
                  {researchMutation.isPending || researchJobId
                    ? "Research in progress…"
                    : "Run research"}
                </button>
              </div>
            </div>
          }
        />
      </Section>

      <ItemGovernanceControls
        assignedTo={item.assignedTo}
        disposition={item.disposition}
        assignmentCapability={assignmentCapability}
        dispositionCapability={dispositionCapability}
        members={assignableMembersQuery.data ?? []}
        dueAt={(item as { dueAt?: string }).dueAt}
        severity={severityWord(item)}
        onAssign={handleAssign}
        onSetDisposition={handleSetDisposition}
      />

      <section className="section" data-testid="decision-action-bar">
        <div className="section-head">
          <div>
            <h2>Your call</h2>
            {/* The server's own explanation of why this action is or is not
                permitted. Focusable so a denial can be read without a mouse. */}
            <p tabIndex={0}>
              Each call is recorded with your name, the script version, and the reason.
            </p>
            <p className="small muted" tabIndex={0}>
              {decisionCapability?.explanation ??
                "Decision capability is unavailable for this item and current role."}
            </p>
          </div>
        </div>

        <Card>
          {feedback && (
            <Banner
              tone={
                feedback.startsWith("Decision not") || feedback.startsWith("This item changed")
                  ? "is-danger"
                  : "is-success"
              }
              icon={
                feedback.startsWith("Decision not") || feedback.startsWith("This item changed")
                  ? "⚠"
                  : "✓"
              }
              message={feedback}
              role="alert"
              className="gap-b-4"
            />
          )}

          <form onSubmit={handleRecordDecision}>
            <fieldset disabled={!decisionCapability?.allowed || decisionMutation.isPending}>
              <legend className="sr-only">Evidence-review outcome</legend>
              <div className="grid grid-3">
                {[
                  {
                    id: "accepted" as const,
                    label: "Verify this source",
                    description: "Use the cited material in continued human review",
                  },
                  {
                    id: "rejected" as const,
                    label: "Rule this source out",
                    description: "Record why the cited material is not reliable",
                  },
                  {
                    id: "further_review_required" as const,
                    label: "Further review required",
                    description: "Keep unresolved risk open for qualified review",
                  },
                ].map((option) => (
                  <div className="stack-sm" key={option.id}>
                    {/* The design system stretches .choice inputs across the pill
                        so the whole chip is clickable. That makes the input the
                        hit target for its own visible label, so it is taken out
                        of the flow here and the wrapping label forwards clicks
                        natively. The :checked + span styling is unaffected. */}
                    <label className="choice">
                      <input
                        className="sr-only"
                        type="radio"
                        name="decision"
                        value={option.id}
                        checked={decision === option.id}
                        onChange={() => setDecision(option.id)}
                      />
                      <span>{option.label}</span>
                    </label>
                    <span className="field-hint">{option.description}</span>
                  </div>
                ))}
              </div>

              <label className="field gap-t-5" htmlFor="rationale">
                <span className="field-label">Accountable rationale</span>
                <textarea
                  id="rationale"
                  required
                  rows={3}
                  value={rationale}
                  onChange={(event) => setRationale(event.target.value)}
                />
              </label>

              <div className="cluster gap-t-4" style={{ justifyContent: "flex-end" }}>
                <button className="button button-primary" type="submit" disabled={!rationale.trim()}>
                  {decisionMutation.isPending ? "Recording…" : "Record Review Decision"}
                </button>
              </div>
            </fieldset>
          </form>
        </Card>
      </section>

      {item.decisions.length > 0 && (
        <Section title="Attributable decision history">
          <div className="stack">
            {item.decisions.map((record) => (
              <article className="source-card" key={record.recordId}>
                <strong>
                  {record.kind}: {record.value}
                </strong>
                <p className="small gap-t-1">{record.rationale}</p>
                <p className="mono small muted gap-t-1">
                  Actor {record.actorId} · version {record.resultingVersion}
                </p>
              </article>
            ))}
          </div>
        </Section>
      )}

      <RewriteProposalCard
        orgSlug={orgSlug}
        projectId={projectId}
        itemId={item.itemId}
        originalText={item.contextText ?? item.entityName}
        proposeCapability={rewriteProposeCapability}
        approveCapability={rewriteApproveCapability}
      />
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
    </Page>
  );
}

export default ItemDetailRoute;

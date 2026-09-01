import React, { useEffect, useState } from "react";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { CommentThread } from "../../../../../../features/collaboration/CommentThread";
import { RewriteProposalCard } from "../../../../../../features/collaboration/RewriteProposalCard";
import { ReferralCard } from "../../../../../../features/collaboration/ReferralCard";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/items/$itemId")({
  component: ItemDetailRoute,
});

export function ItemDetailRoute() {
  const { orgSlug, projectId, itemId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/items/$itemId",
  });
  const [item, setItem] = useState<any>(null);
  const [decision, setDecision] = useState("cleared");
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadItem = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await api.getClearanceItem({
        path: { org_id: orgSlug, project_id: projectId, item_id: itemId },
      });
      if (res.ok && res.value.data) {
        setItem(res.value.data);
      } else {
        setItem(null);
        setLoadError(res.ok ? "Item not found." : res.error.message || "Failed to load item.");
      }
    } catch {
      setItem(null);
      setLoadError("Unable to reach the clearance service.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItem();
  }, [orgSlug, projectId, itemId]);

  const handleRecordDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rationale.trim()) return;
    setSubmitting(true);
    setFeedback(null);

    try {
      const res = await api.recordEvidenceDecision({
        path: { org_id: orgSlug, project_id: projectId, item_id: itemId },
        body: { decision, rationale },
      });

      if (!res.ok) {
        setFeedback(`Error: ${res.error.message || "Failed to record decision"}`);
        return;
      }

      setFeedback("Decision recorded and committed to immutable audit log.");
      // Reload authoritative state rather than optimistically inventing it.
      await loadItem();
    } catch {
      // A governed decision must not report fake success. Surface the failure.
      setFeedback("Error: could not reach the clearance service. Your decision was not recorded.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-xs text-slate-400 font-sans">Loading clearance item…</div>;
  }

  if (loadError || !item) {
    return (
      <div className="p-6 max-w-2xl font-sans space-y-3">
        <Link
          to="/o/$orgSlug/projects/$projectId/workspace"
          params={{ orgSlug, projectId }}
          className="text-xs text-amber-500 hover:underline inline-block"
        >
          ← Back to Screenplay Workspace
        </Link>
        <div role="alert" className="p-4 rounded bg-red-950/50 border border-red-900 text-red-400 text-xs">
          {loadError || "This clearance item is not available."}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl font-sans">
      <div className="flex items-center justify-between">
        <div>
          <Link
            to="/o/$orgSlug/projects/$projectId/workspace"
            params={{ orgSlug, projectId }}
            className="text-xs text-amber-500 hover:underline mb-1 inline-block"
          >
            ← Back to Screenplay Workspace
          </Link>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-3">
            <span>{item.text}</span>
            <span className="text-xs px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-normal">
              {item.category}
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Scene {item.scene} • Page {item.page} • Status:{" "}
            <span className="font-bold text-amber-400 uppercase">{item.status}</span>
          </p>
        </div>
      </div>

      {/* Sourced Evidence Claims */}
      <div className="space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
          Source Snapshots & Evidence Claims ({item.claims?.length || 0})
        </h2>

        {item.claims?.map((claim: any) => (
          <div key={claim.claim_id} className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-2">
            <div className="flex items-center justify-between">
              <a
                href={claim.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-bold text-amber-400 hover:underline"
              >
                {claim.source_title} ↗
              </a>
              <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-mono">
                {claim.authority || claim.publisher}
              </span>
            </div>
            <p className="text-xs text-slate-300 italic border-l-2 border-slate-700 pl-3">
              "{claim.excerpt || claim.claim_text}"
            </p>
          </div>
        ))}
      </div>

      {/* Decision Recording Form */}
      <div data-testid="decision-action-bar" className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 shadow-sm">
        <h3 className="text-sm font-bold text-white">Record Clearance Decision</h3>
        {feedback && (
          <div
            role="alert"
            className={`p-3 rounded text-xs ${
              feedback.startsWith("Error")
                ? "bg-red-950/50 border border-red-900 text-red-400"
                : "bg-emerald-950/50 border border-emerald-900 text-emerald-400"
            }`}
          >
            {feedback}
          </div>
        )}

        <form onSubmit={handleRecordDecision} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { id: "cleared", label: "Clear Item", desc: "No legal risk identified" },
              { id: "needs_rewrite", label: "Flag for Rewrite", desc: "Requires fictionalization" },
              { id: "escalated", label: "Refer to Counsel", desc: "Escalate for legal opinion" },
            ].map((opt) => (
              <label
                key={opt.id}
                className={`p-3 rounded border cursor-pointer transition-all ${
                  decision === opt.id
                    ? "bg-amber-950/30 border-amber-500 text-white"
                    : "bg-slate-800/60 border-slate-700 text-slate-300 hover:border-slate-600"
                }`}
              >
                <input
                  type="radio"
                  name="decision"
                  value={opt.id}
                  checked={decision === opt.id}
                  onChange={(e) => setDecision(e.target.value)}
                  className="sr-only"
                />
                <div className="text-xs font-bold">{opt.label}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{opt.desc}</div>
              </label>
            ))}
          </div>

          <div>
            <label htmlFor="rationale" className="block text-xs font-medium text-slate-300 mb-1">
              Accountable Rationale (Committed to Immutable Audit Log)
            </label>
            <textarea
              id="rationale"
              required
              rows={3}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="e.g. Verified with primary registry record; no trademark conflict in class 09."
              className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-xs font-bold text-white rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              {submitting ? "Committing Decision..." : "Commit Governed Decision"}
            </button>
          </div>
        </form>
      </div>

      {/* Rewrite Proposals Section */}
      <RewriteProposalCard originalText={item.text} />

      {/* Specialist Referral Section */}
      <ReferralCard itemId={item.id} />

      {/* Comments & Collaboration Section */}
      <CommentThread />
    </div>
  );
}

export default ItemDetailRoute;

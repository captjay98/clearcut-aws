import React, { useState } from "react";

export interface RewriteProposal {
  id: string;
  originalText: string;
  proposedText: string;
  rationale: string;
  status: "pending" | "approved" | "rejected";
}

export interface RewriteProposalCardProps {
  originalText?: string;
  proposals?: RewriteProposal[];
  onPropose?: (proposedText: string, rationale: string) => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}

export function RewriteProposalCard({
  originalText = "Vega Camera",
  proposals = [],
  onPropose,
  onApprove,
  onReject,
}: RewriteProposalCardProps) {
  const [proposedText, setProposedText] = useState("");
  const [rationale, setRationale] = useState("");
  const [localProposals, setLocalProposals] = useState<RewriteProposal[]>(
    proposals.length > 0
      ? proposals
      : [
          {
            id: "rw-1",
            originalText,
            proposedText: "Aero Optics Mark IV",
            rationale: "Fictional camera model avoiding registered trademark in Class 09.",
            status: "pending",
          },
        ]
  );

  const handlePropose = (e: React.FormEvent) => {
    e.preventDefault();
    if (!proposedText.trim()) return;

    const prop: RewriteProposal = {
      id: `rw-${Date.now()}`,
      originalText,
      proposedText,
      rationale: rationale || "Fictional replacement proposed for clearance safety.",
      status: "pending",
    };

    setLocalProposals((prev) => [...prev, prop]);
    onPropose?.(proposedText, rationale);
    setProposedText("");
    setRationale("");
  };

  const handleApprove = (id: string) => {
    setLocalProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "approved" as const } : p))
    );
    onApprove?.(id);
  };

  const handleReject = (id: string) => {
    setLocalProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "rejected" as const } : p))
    );
    onReject?.(id);
  };

  return (
    <div data-testid="rewrite-proposals-section" className="space-y-4 font-sans">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Rewrite & Fictionalization Proposals</span>
        <span className="text-[10px] text-amber-400 font-normal">Script Lineage Bound</span>
      </div>

      {/* Proposals list with diffs */}
      <div className="space-y-3">
        {localProposals.map((p) => (
          <div key={p.id} className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-3 shadow-sm">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 bg-red-950/20 border border-red-900/40 rounded">
                <span className="text-[10px] font-bold uppercase text-red-400">Original Script Text</span>
                <div className="font-mono text-slate-200 mt-1 line-through">{p.originalText}</div>
              </div>
              <div className="p-2.5 bg-emerald-950/20 border border-emerald-900/40 rounded">
                <span className="text-[10px] font-bold uppercase text-emerald-400">Proposed Fictionalization</span>
                <div className="font-mono text-emerald-300 font-bold mt-1">{p.proposedText}</div>
              </div>
            </div>

            <p className="text-xs text-slate-400 italic">"{p.rationale}"</p>

            <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                  p.status === "approved"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                    : p.status === "rejected"
                    ? "bg-red-950 text-red-400 border border-red-800"
                    : "bg-amber-950 text-amber-400 border border-amber-800"
                }`}
              >
                {p.status}
              </span>

              {p.status === "pending" && (
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={() => handleReject(p.id)}
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded"
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApprove(p.id)}
                    className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded shadow"
                  >
                    Approve Rewrite
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Propose new rewrite */}
      <form onSubmit={handlePropose} className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg space-y-3">
        <h4 className="text-xs font-bold text-slate-200">Propose Alternative Script Phrasing</h4>
        <div className="space-y-2">
          <input
            type="text"
            required
            value={proposedText}
            onChange={(e) => setProposedText(e.target.value)}
            placeholder="e.g. Lumina Optics Cam 9"
            className="w-full px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
          <input
            type="text"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Rationale for clearance team / writer..."
            className="w-full px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!proposedText.trim()}
            className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow"
          >
            Submit Proposal
          </button>
        </div>
      </form>
    </div>
  );
}

export default RewriteProposalCard;

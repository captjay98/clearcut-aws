import React, { useState } from "react";

export interface ReferralCardProps {
  itemId: string;
  onRefer?: (role: string, notes: string) => void;
}

export function ReferralCard({ itemId, onRefer }: ReferralCardProps) {
  const [targetRole, setTargetRole] = useState("counsel");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<"idle" | "referred" | "acknowledged">("idle");

  const handleRefer = (e: React.FormEvent) => {
    e.preventDefault();
    if (!notes.trim()) return;
    setStatus("referred");
    onRefer?.(targetRole, notes);
  };

  const handleAcknowledge = () => {
    setStatus("acknowledged");
  };

  return (
    <div data-testid="referral-section" className="space-y-4 font-sans">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Specialist Referral Workflow</span>
        <span className="text-[10px] text-slate-500 font-normal">Multi-Discipline Sign-Off</span>
      </div>

      <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-3 shadow-sm">
        {status === "idle" ? (
          <form onSubmit={handleRefer} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div>
                <label htmlFor="target-role" className="block text-slate-400 font-medium mb-1">
                  Refer To Specialist Role
                </label>
                <select
                  id="target-role"
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-white text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  <option value="counsel">Legal Counsel (External/Production)</option>
                  <option value="trademark_specialist">Trademark & Title Specialist</option>
                  <option value="music_supervisor">Music Clearance Supervisor</option>
                  <option value="lead_producer">Lead Production Executive</option>
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="referral-notes" className="block text-slate-400 font-medium mb-1 text-xs">
                Referral Instructions & Specific Legal Questions
              </label>
              <textarea
                id="referral-notes"
                required
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Please review commercial context of mark usage in scene 1."
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-white text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded shadow"
              >
                Send Formal Referral
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-xs font-bold text-slate-200">
                Referred to <span className="text-amber-400 capitalize">{targetRole.replace("_", " ")}</span>
              </div>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                  status === "acknowledged"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                    : "bg-amber-950 text-amber-400 border border-amber-800"
                }`}
              >
                {status}
              </span>
            </div>
            <p className="text-xs text-slate-400 italic">"{notes || "Pending specialist review."}"</p>

            {status === "referred" && (
              <div className="pt-2 flex justify-end">
                <button
                  type="button"
                  onClick={handleAcknowledge}
                  className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded shadow"
                >
                  Acknowledge Referral
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ReferralCard;

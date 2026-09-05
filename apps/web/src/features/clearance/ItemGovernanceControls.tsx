import type { ClearanceDisposition, ItemCapability } from "@clearcut/contracts";
import React, { useState } from "react";

export interface ItemGovernanceControlsProps {
  assignedTo?: string | null;
  disposition?: ClearanceDisposition | null;
  assignmentCapability?: ItemCapability;
  dispositionCapability?: ItemCapability;
  onAssign?: (assigneeId: string | null) => Promise<void>;
  onSetDisposition?: (
    disposition: ClearanceDisposition,
    rationale: string,
  ) => Promise<void>;
}

export function ItemGovernanceControls({
  assignedTo,
  disposition,
  assignmentCapability,
  dispositionCapability,
  onAssign,
  onSetDisposition,
}: ItemGovernanceControlsProps) {
  const [assigneeId, setAssigneeId] = useState(assignedTo ?? "");
  const [assignmentError, setAssignmentError] = useState<string | null>(null);
  const [isAssigning, setIsAssigning] = useState(false);
  const [selectedDisposition, setSelectedDisposition] = useState<ClearanceDisposition>(
    disposition ?? "pending",
  );
  const [dispositionRationale, setDispositionRationale] = useState("");
  const [dispositionError, setDispositionError] = useState<string | null>(null);
  const [isSettingDisposition, setIsSettingDisposition] = useState(false);
  const assignmentAllowed = assignmentCapability?.allowed ?? Boolean(onAssign);
  const dispositionAllowed = dispositionCapability?.allowed ?? Boolean(onSetDisposition);

  const handleAssignment = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!onAssign || !assignmentAllowed) return;

    setAssignmentError(null);
    setIsAssigning(true);
    try {
      await onAssign(assigneeId.trim() || null);
    } catch (submissionError) {
      setAssignmentError(
        submissionError instanceof Error
          ? submissionError.message
          : "The assignment was not recorded.",
      );
    } finally {
      setIsAssigning(false);
    }
  };

  const handleDisposition = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!onSetDisposition || !dispositionAllowed || !dispositionRationale.trim()) return;

    setDispositionError(null);
    setIsSettingDisposition(true);
    try {
      await onSetDisposition(selectedDisposition, dispositionRationale.trim());
      setDispositionRationale("");
    } catch (submissionError) {
      setDispositionError(
        submissionError instanceof Error
          ? submissionError.message
          : "The disposition was not recorded.",
      );
    } finally {
      setIsSettingDisposition(false);
    }
  };

  return (
    <section
      aria-label="Item governance controls"
      className="rounded-lg border border-slate-800 bg-slate-900 p-4"
    >
      <h2 className="text-sm font-bold text-white">Assignment & Disposition</h2>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <form onSubmit={handleAssignment} className="space-y-2">
          <p tabIndex={0} className="text-xs text-slate-400">
            {assignmentCapability?.explanation ??
              "Assignment capability is unavailable for this item and current role."}
          </p>
          <label htmlFor="assignee-member-id" className="block text-xs text-slate-300">
            Assignee member ID
          </label>
          <input
            id="assignee-member-id"
            value={assigneeId}
            disabled={!assignmentAllowed}
            onChange={(event) => setAssigneeId(event.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white disabled:opacity-50"
          />
          {assignmentError ? (
            <p role="alert" className="text-xs text-rose-300">
              {assignmentError}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={!assignmentAllowed || !onAssign || isAssigning}
            className="rounded bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {isAssigning ? "Saving…" : "Save Assignment"}
          </button>
        </form>

        <form onSubmit={handleDisposition} className="space-y-2">
          <p tabIndex={0} className="text-xs text-slate-400">
            {dispositionCapability?.explanation ??
              "Disposition capability is unavailable for this item and current role."}
          </p>
          <label htmlFor="item-disposition" className="block text-xs text-slate-300">
            Disposition
          </label>
          <select
            id="item-disposition"
            value={selectedDisposition}
            disabled={!dispositionAllowed}
            onChange={(event) =>
              setSelectedDisposition(event.target.value as ClearanceDisposition)
            }
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white disabled:opacity-50"
          >
            <option value="pending">Pending</option>
            <option value="verified">Verified evidence state</option>
            <option value="ruled_out">Ruled out</option>
            <option value="fixed_in_rewrite">Fixed in rewrite</option>
            <option value="deferred">Deferred for qualified review</option>
          </select>
          <label htmlFor="disposition-rationale" className="block text-xs text-slate-300">
            Disposition rationale
          </label>
          <textarea
            id="disposition-rationale"
            rows={2}
            value={dispositionRationale}
            disabled={!dispositionAllowed}
            onChange={(event) => setDispositionRationale(event.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white disabled:opacity-50"
          />
          {dispositionError ? (
            <p role="alert" className="text-xs text-rose-300">
              {dispositionError}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={
              !dispositionAllowed ||
              !onSetDisposition ||
              isSettingDisposition ||
              !dispositionRationale.trim()
            }
            className="rounded bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {isSettingDisposition ? "Saving…" : "Save Disposition"}
          </button>
        </form>
      </div>
    </section>
  );
}

export default ItemGovernanceControls;

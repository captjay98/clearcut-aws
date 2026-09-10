import type { ClearanceDisposition, ItemCapability, Membership } from "@clearcut/contracts";
import React, { useState } from "react";
import { Banner, Card } from "../../components/ds";

export interface ItemGovernanceControlsProps {
  assignedTo?: string | null;
  disposition?: ClearanceDisposition | null;
  assignmentCapability?: ItemCapability;
  dispositionCapability?: ItemCapability;
  members?: Membership[];
  dueAt?: string | null;
  severity?: "High" | "Medium" | "Low";
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
  members = [],
  dueAt,
  severity,
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
  const assignedMember = members.find((member) => member.userId === assignedTo);

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
    <section className="section" aria-label="Item governance controls">
      <div className="section-head">
        <div>
          <h2>Ownership</h2>
          <p className="small muted">
            Each call is recorded with your name, the script version, and the reason.
          </p>
        </div>
      </div>

      <div className="grid grid-2">
        <Card>
          <h3>Ownership</h3>
          <dl className="gap-t-3">
            <dt className="small muted">Assignee</dt>
            <dd>{assignedMember?.email ?? (assignedTo ? assignedTo : "Unassigned")}</dd>
            <dt className="small muted">Due</dt>
            <dd>
              {dueAt
                ? new Date(dueAt).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })
                : "—"}
            </dd>
            <dt className="small muted">Priority</dt>
            <dd>{severity ?? "—"}</dd>
          </dl>

          <form onSubmit={handleAssignment} className="gap-t-4">
            {/* The server's reason this action is or is not permitted, focusable
                so a denial is reachable without a mouse. */}
            <p className="small muted" tabIndex={0}>
              {assignmentCapability?.explanation ??
                "Assignment capability is unavailable for this item and current role."}
            </p>

            <label className="field gap-t-4" htmlFor="assignee-member-id">
              <span className="field-label">Assignee</span>
              {members.length > 0 ? (
                <select
                  id="assignee-member-id"
                  value={assigneeId}
                  disabled={!assignmentAllowed}
                  onChange={(event) => setAssigneeId(event.target.value)}
                >
                  <option value="">Unassigned</option>
                  {members.map((member) => (
                    <option key={member.userId} value={member.userId}>
                      {member.email ?? member.userId}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="assignee-member-id"
                  value={assigneeId}
                  disabled={!assignmentAllowed}
                  onChange={(event) => setAssigneeId(event.target.value)}
                  placeholder="Member id"
                />
              )}
            </label>

            {assignmentError && (
              <Banner
                tone="is-danger"
                icon="⚠"
                message={assignmentError}
                role="alert"
                className="gap-t-3"
              />
            )}

            <div className="cluster gap-t-4">
              <button
                className="button button-primary button-sm"
                type="submit"
                disabled={!assignmentAllowed || !onAssign || isAssigning}
              >
                {isAssigning ? "Saving…" : "Reassign"}
              </button>
            </div>
          </form>
        </Card>

        <Card>
          <h3>Disposition</h3>
          <form onSubmit={handleDisposition} className="gap-t-3">
            <p className="small muted" tabIndex={0}>
              {dispositionCapability?.explanation ??
                "Disposition capability is unavailable for this item and current role."}
            </p>
            <label className="field" htmlFor="disposition">
              <span className="field-label">Disposition</span>
              <select
                id="disposition"
                value={selectedDisposition}
                disabled={!dispositionAllowed}
                onChange={(event) =>
                  setSelectedDisposition(event.target.value as ClearanceDisposition)
                }
              >
                <option value="pending">Pending</option>
                <option value="verified">Verified evidence state</option>
                <option value="ruled_out">Ruled out</option>
                <option value="fixed_in_rewrite">Fixed in rewrite</option>
                <option value="deferred">Deferred for qualified review</option>
              </select>
            </label>
            <label className="field" htmlFor="disposition-rationale">
              <span className="field-label">Disposition rationale</span>
              <textarea
                id="disposition-rationale"
                rows={2}
                value={dispositionRationale}
                disabled={!dispositionAllowed}
                onChange={(event) => setDispositionRationale(event.target.value)}
              />
            </label>
            {dispositionError && (
              <Banner
                tone="is-danger"
                icon="⚠"
                message={dispositionError}
                role="alert"
              />
            )}
            <button
              className="button button-primary button-sm"
              type="submit"
              disabled={
                !dispositionAllowed || !onSetDisposition || !dispositionRationale.trim() || isSettingDisposition
              }
            >
              {isSettingDisposition ? "Saving…" : "Save Disposition"}
            </button>
          </form>
        </Card>
      </div>
    </section>
  );
}
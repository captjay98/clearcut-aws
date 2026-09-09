import type { ClearanceDisposition, ItemCapability } from "@clearcut/contracts";
import React, { useState } from "react";
import { Banner, Card } from "../../components/ds";

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
    <section className="section" aria-label="Item governance controls">
      <div className="section-head">
        <div>
          <h2>Assignment &amp; disposition</h2>
        </div>
      </div>

      <div className="grid grid-2">
        <Card>
          <form onSubmit={handleAssignment}>
            {/* The server's reason this action is or is not permitted, focusable
                so a denial is reachable without a mouse. */}
            <p className="small muted" tabIndex={0}>
              {assignmentCapability?.explanation ??
                "Assignment capability is unavailable for this item and current role."}
            </p>

            <label className="field gap-t-4" htmlFor="assignee-member-id">
              <span className="field-label">Assignee member ID</span>
              <input
                id="assignee-member-id"
                value={assigneeId}
                disabled={!assignmentAllowed}
                onChange={(event) => setAssigneeId(event.target.value)}
              />
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
                {isAssigning ? "Saving…" : "Save Assignment"}
              </button>
            </div>
          </form>
        </Card>

        <Card>
          <form onSubmit={handleDisposition}>
            <p className="small muted" tabIndex={0}>
              {dispositionCapability?.explanation ??
                "Disposition capability is unavailable for this item and current role."}
            </p>

            {/* The label is a sibling rather than a wrapper. A <label> that wraps
                a <select> folds the selected option's text into the accessible
                name, so the control would be named "Disposition Pending". */}
            <div className="field gap-t-4">
              <label className="field-label" htmlFor="item-disposition">
                Disposition
              </label>
              <select
                id="item-disposition"
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
            </div>

            <label className="field gap-t-4" htmlFor="disposition-rationale">
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
                className="gap-t-3"
              />
            )}

            <div className="cluster gap-t-4">
              <button
                className="button button-primary button-sm"
                type="submit"
                disabled={
                  !dispositionAllowed ||
                  !onSetDisposition ||
                  isSettingDisposition ||
                  !dispositionRationale.trim()
                }
              >
                {isSettingDisposition ? "Saving…" : "Save Disposition"}
              </button>
            </div>
          </form>
        </Card>
      </div>
    </section>
  );
}

export default ItemGovernanceControls;

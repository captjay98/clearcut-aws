import React, { useState } from "react";
import { Dialog } from "@clearcut/design-system";

export interface DecisionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (decisionType: string, rationale: string) => void;
  itemText: string;
}

export function DecisionDialog({ isOpen, onClose, onSubmit, itemText }: DecisionDialogProps) {
  const [decisionType, setDecisionType] = useState("accept_as_is");
  const [rationale, setRationale] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!rationale.trim()) return;
    onSubmit(decisionType, rationale);
    onClose();
  };

  return (
    <Dialog isOpen={isOpen} onClose={onClose} title={`Record Evidence Decision: ${itemText}`}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
            Governed Action
          </label>
          <select
            value={decisionType}
            onChange={(e) => setDecisionType(e.target.value)}
            className="w-full p-2 border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800 text-sm"
          >
            <option value="accept_as_is">Accept Evidence As-Is (Clear)</option>
            <option value="request_rewrite">Request Script Rewrite</option>
            <option value="seek_license">Seek Commercial License</option>
            <option value="flag_blocker">Flag as Blocking Risk</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
            Decision Rationale (Required)
          </label>
          <textarea
            required
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="State evidence grounding and reason for decision..."
            className="w-full p-2 border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800 text-sm"
          />
        </div>

        <div className="flex justify-end space-x-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-slate-300 dark:border-slate-700 rounded text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm font-medium"
          >
            Commit Governed Decision
          </button>
        </div>
      </form>
    </Dialog>
  );
}

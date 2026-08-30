import React, { useState } from "react";
import { Dialog, Badge } from "@clearcut/design-system";

export interface ReleaseDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (attestation: string) => void;
  versionLabel: string;
}

export function ReleaseDialog({
  isOpen,
  onClose,
  onConfirm,
  versionLabel,
}: ReleaseDialogProps) {
  const [attestation, setAttestation] = useState(
    "I attest that this clearance dossier is accurate and complete based on current review findings."
  );

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Release this frozen snapshot?"
    >
      <div className="space-y-4 text-xs">
        <p className="text-slate-600 dark:text-slate-400">
          Releasing binds this dossier immutably to <strong>{versionLabel}</strong> and enables authorized distribution.
        </p>

        <div className="space-y-2">
          <label className="font-medium text-slate-700 dark:text-slate-300">
            Human Attestation & Accountability Statement:
          </label>
          <textarea
            value={attestation}
            onChange={(e) => setAttestation(e.target.value)}
            rows={3}
            className="w-full p-2 border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
          />
        </div>

        <div className="flex justify-end space-x-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 border border-slate-300 dark:border-slate-700 rounded text-slate-700 dark:text-slate-300"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(attestation)}
            className="px-3 py-1.5 bg-blue-600 text-white font-medium rounded hover:bg-blue-700"
          >
            Release Report
          </button>
        </div>
      </div>
    </Dialog>
  );
}

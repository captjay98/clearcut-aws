import React, { useState } from "react";

interface ParseWarning {
  warningCode: string;
  message: string;
}

interface ParseReviewProps {
  title: string;
  sceneCount: number;
  elementCount: number;
  warnings?: ParseWarning[];
  onConfirm: () => void;
  onCancel: () => void;
}

export function ParseReview({
  title,
  sceneCount,
  elementCount,
  warnings = [],
  onConfirm,
  onCancel,
}: ParseReviewProps) {
  const [acknowledged, setAcknowledged] = useState(warnings.length === 0);

  return (
    <div className="space-y-6">
      <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-800">
        <h3 className="font-semibold text-slate-900 dark:text-white text-lg mb-2">{title}</h3>
        <div className="grid grid-cols-2 gap-4 text-sm text-slate-600 dark:text-slate-400">
          <div>
            <span className="font-medium">Scenes Detected:</span> {sceneCount}
          </div>
          <div>
            <span className="font-medium">Total Elements:</span> {elementCount}
          </div>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-lg">
          <h4 className="font-medium text-amber-800 dark:text-amber-400 text-sm mb-2">
            Parse Warnings ({warnings.length})
          </h4>
          <ul className="list-disc list-inside text-xs text-amber-700 dark:text-amber-300 space-y-1 mb-4">
            {warnings.map((w, idx) => (
              <li key={idx}>{w.message}</li>
            ))}
          </ul>
          <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="rounded text-blue-600"
            />
            I have reviewed the parse warnings and want to proceed with Version 1.
          </label>
        </div>
      )}

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border border-slate-300 dark:border-slate-700 rounded text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50"
        >
          Back
        </button>
        <button
          type="button"
          disabled={!acknowledged}
          onClick={onConfirm}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          Commit Script Version 1
        </button>
      </div>
    </div>
  );
}

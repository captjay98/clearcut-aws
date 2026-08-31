import React from "react";

export interface CadenceSelectorProps {
  currentCadence: string;
  onChangeCadence: (cadence: string) => void;
  disabled?: boolean;
}

export function CadenceSelector({
  currentCadence = "weekly",
  onChangeCadence,
  disabled = false,
}: CadenceSelectorProps) {
  const options = [
    { id: "weekly", label: "Weekly (Recommended)", desc: "Scans active trademark & entity registries every 7 days" },
    { id: "bi-weekly", label: "Bi-Weekly", desc: "Scans sources every 14 days" },
    { id: "monthly", label: "Monthly", desc: "Scans sources on the 1st of every month" },
  ];

  return (
    <div data-testid="cadence-selector" className="space-y-3 font-sans">
      <label className="block text-xs font-bold uppercase tracking-wider text-slate-400">
        Continuous Monitoring Cadence
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => onChangeCadence(opt.id)}
            className={`p-3.5 rounded-lg border text-left transition-all ${
              currentCadence === opt.id
                ? "bg-amber-950/30 border-amber-500 text-white ring-1 ring-amber-500/40"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <div className="text-xs font-bold capitalize">{opt.label}</div>
            <div className="text-[10px] text-slate-500 mt-1 leading-snug">{opt.desc}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default CadenceSelector;

import React from "react";

export type MonitoringCadence = "daily" | "weekly" | "biweekly" | "monthly";

export interface CadenceSelectorProps {
  currentCadence: MonitoringCadence;
  onChangeCadence: (cadence: MonitoringCadence) => void;
  disabled?: boolean;
}

const options: ReadonlyArray<{
  id: MonitoringCadence;
  label: string;
  desc: string;
}> = [
  {
    id: "weekly",
    label: "Weekly (Recommended)",
    desc: "Scans active trademark and entity registries every 7 days",
  },
  {
    id: "biweekly",
    label: "Biweekly",
    desc: "Scans sources every 14 days",
  },
  {
    id: "monthly",
    label: "Monthly",
    desc: "Scans sources on the first day of every month",
  },
];

export function CadenceSelector({
  currentCadence,
  onChangeCadence,
  disabled = false,
}: CadenceSelectorProps) {
  return (
    <div data-testid="cadence-selector" className="space-y-3 font-sans">
      <p className="block text-xs font-bold uppercase tracking-wider text-slate-400">
        Continuous Monitoring Cadence
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            onClick={() => onChangeCadence(option.id)}
            className={`p-3.5 rounded-lg border text-left transition-all ${
              currentCadence === option.id
                ? "bg-amber-950/30 border-amber-500 text-white ring-1 ring-amber-500/40"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <span className="block text-xs font-bold capitalize">{option.label}</span>
            <span className="mt-1 block text-[10px] leading-snug text-slate-500">
              {option.desc}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default CadenceSelector;

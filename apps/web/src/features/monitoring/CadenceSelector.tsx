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
    <div className="stack-sm" data-testid="cadence-selector">
      <span className="field-label">Continuous monitoring cadence</span>
      <div className="grid grid-3">
        {options.map((option) => (
          <div className="stack-sm" key={option.id}>
            {/* sr-only input so the visible chip is the click target rather than
                the input the design system stretches over it. */}
            <label className="choice">
              <input
                className="sr-only"
                type="radio"
                name="monitoring-cadence"
                value={option.id}
                checked={currentCadence === option.id}
                disabled={disabled}
                onChange={() => onChangeCadence(option.id)}
              />
              <span>{option.label}</span>
            </label>
            <span className="field-hint">{option.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CadenceSelector;

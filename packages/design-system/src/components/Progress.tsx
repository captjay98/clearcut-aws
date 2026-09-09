import React from "react";

export interface ProgressProps {
  value: number;
  max?: number;
  label?: string;
}

export function Progress({ value, max = 100, label }: ProgressProps) {
  const percentage = Math.min(Math.max(0, (value / max) * 100), 100);

  return (
    <div>
      {label && (
        <div className="cluster-between gap-b-3">
          <span className="small muted">{label}</span>
          <span className="mono">{Math.round(percentage)}%</span>
        </div>
      )}
      <div className="progress">
        <span
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={max}
          aria-label={label}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

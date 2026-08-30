import React from "react";

export interface StatItem {
  label: string;
  value: string | number;
  description?: string;
}

export interface StatGridProps {
  stats: StatItem[];
}

export function StatGrid({ stats }: StatGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((s, idx) => (
        <div
          key={idx}
          className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg shadow-sm"
        >
          <dt className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            {s.label}
          </dt>
          <dd className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">{s.value}</dd>
          {s.description && (
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{s.description}</p>
          )}
        </div>
      ))}
    </div>
  );
}

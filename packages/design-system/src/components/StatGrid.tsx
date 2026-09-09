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
    <div className="grid grid-4">
      {stats.map((stat) => (
        <div className="stat" key={stat.label}>
          <span className="stat-label">{stat.label}</span>
          <span className="stat-value">{stat.value}</span>
          {stat.description && <span className="stat-hint">{stat.description}</span>}
        </div>
      ))}
    </div>
  );
}

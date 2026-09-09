import type { OrganizationSettings } from "@clearcut/contracts";

export type MonitoringCadence = OrganizationSettings["defaultMonitoringCadence"];

/**
 * Cadence is stored canonically as a token and never displayed as one.
 *
 * `manual` on its own does not tell a reader that nothing happens until they ask,
 * and `off` does not say monitoring is paused. Every rendering of the value goes
 * through this map, so the two readings of one value cannot drift apart.
 */
export const CADENCE_LABELS: Readonly<Record<MonitoringCadence, string>> = {
  off: "Off",
  manual: "Manual only",
  daily: "Daily",
  weekly: "Weekly",
};

export const CADENCE_ORDER: readonly MonitoringCadence[] = [
  "off",
  "manual",
  "daily",
  "weekly",
];

export function cadenceLabel(value: string): string {
  return CADENCE_LABELS[value as MonitoringCadence] ?? value;
}

export function isMonitoringCadence(value: string): value is MonitoringCadence {
  return value in CADENCE_LABELS;
}

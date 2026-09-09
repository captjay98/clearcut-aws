import type { ClearanceItem } from "@clearcut/contracts";
import type { Tone } from "../../components/ds";

/**
 * Presentation rules shared by every surface that shows clearance items: the
 * screenplay margin, the scene rail, the flag list and the item detail. Kept in
 * one place so a status never reads as settled on one surface and open on
 * another.
 */

/** Statuses that mean a person still has to act before delivery. */
export const ATTENTION_STATUSES = new Set([
  "needs_review",
  "conflict",
  "referred",
  "blocked",
  "unresolved",
]);

const SETTLED_STATUSES = new Set(["verified", "ruled_out", "cleared", "closed", "resolved"]);

export function isAttention(item: ClearanceItem): boolean {
  return ATTENTION_STATUSES.has(item.status);
}

export function statusTone(status: string): Tone {
  if (SETTLED_STATUSES.has(status)) {
    return "is-success";
  }
  if (status === "conflict" || status === "blocked") {
    return "is-danger";
  }
  if (ATTENTION_STATUSES.has(status)) {
    return "is-warning";
  }
  return "";
}

/**
 * Severity vocabulary from the mock's severityOf(): a blocking status outranks
 * everything, then conflicts, then anything still awaiting a decision.
 * The contract carries no severity field, so it is derived from status rather
 * than invented.
 */
export function severityOf(item: ClearanceItem): { severityClass: string; glyph: string } {
  if (item.status === "blocked") {
    return { severityClass: "is-blocked", glyph: "■" };
  }
  if (item.status === "conflict") {
    return { severityClass: "is-high", glyph: "▲" };
  }
  if (ATTENTION_STATUSES.has(item.status)) {
    return { severityClass: "is-medium", glyph: "●" };
  }
  return { severityClass: "is-low", glyph: "○" };
}

/** The mock's SHORT map: the abbreviation printed in the script margin. */
const SHORT_CATEGORY: Record<string, string> = {
  "people & likeness": "PEOPLE",
  "names & characters": "NAMES",
  "brands & trademarks": "MARK",
  "products & trade dress": "PRODUCT",
  "locations & property": "LOCATION",
  "music & lyrics": "MUSIC",
  "artwork & media": "ART",
  "dialogue & quotations": "QUOTE",
  "organizations & insignia": "INSIGNIA",
  "privacy & sensitive facts": "PRIVACY",
};

export function shortCategory(category: string): string {
  const normalized = category.toLowerCase().replace(/_/g, " ");
  const mapped = SHORT_CATEGORY[normalized];
  if (mapped) {
    return mapped;
  }
  // An unmapped category still needs a margin label, so use its first word.
  return normalized.split(/[\s&]+/)[0].slice(0, 8).toUpperCase();
}

export function humanizeStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function humanizeCategory(category: string): string {
  return category.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

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

/** Severity word for list rows and the mock's High/Medium/Low priority lede. */
export function severityWord(item: {
  status: string;
  severity?: "High" | "Medium" | "Low";
}): "High" | "Medium" | "Low" {
  if (item.severity === "High" || item.severity === "Medium" || item.severity === "Low") {
    return item.severity;
  }
  if (item.status === "blocked") return "High";
  if (item.status === "conflict") return "High";
  if (ATTENTION_STATUSES.has(item.status)) return "Medium";
  return "Low";
}

/**
 * Canonical mock category labels. Keys are the backend enum values (underscores
 * become spaces for lookup). Storage values never change — this is display only.
 */
const CATEGORY_BY_API: Record<string, { label: string; short: string }> = {
  real_persons_living: { label: "People & likeness", short: "PEOPLE" },
  real_persons_deceased: { label: "People & likeness", short: "PEOPLE" },
  corporate_entities: { label: "Organizations & insignia", short: "INSIGNIA" },
  products_and_trademarks: { label: "Brands & trademarks", short: "MARK" },
  copyrighted_works: { label: "Artwork & media", short: "ART" },
  music_and_lyrics: { label: "Music & lyrics", short: "MUSIC" },
  locations_and_landmarks: { label: "Locations & property", short: "LOCATION" },
  vehicles_and_insignia: { label: "Products & trade dress", short: "PRODUCT" },
  sensitive_historical_events: { label: "Privacy & sensitive facts", short: "PRIVACY" },
  contact_information: { label: "Dialogue & quotations", short: "QUOTE" },
};

/** Every API category enum value, in mock display order. */
export const API_CATEGORY_VALUES = [
  "real_persons_living",
  "real_persons_deceased",
  "corporate_entities",
  "products_and_trademarks",
  "copyrighted_works",
  "music_and_lyrics",
  "locations_and_landmarks",
  "vehicles_and_insignia",
  "sensitive_historical_events",
  "contact_information",
] as const;

/**
 * Unique mock labels for filter chips. Living/deceased people collapse to one
 * chip so the rail never shows the same display name twice.
 */
export const FILTER_CATEGORY_LABELS: readonly string[] = [
  "People & likeness",
  "Organizations & insignia",
  "Brands & trademarks",
  "Artwork & media",
  "Music & lyrics",
  "Locations & property",
  "Products & trade dress",
  "Privacy & sensitive facts",
  "Dialogue & quotations",
];

function categoryKey(category: string): string {
  return category.toLowerCase().trim();
}

/** Mock display label for an API category enum (or already-humanized value). */
export function displayCategory(category: string): string {
  const key = categoryKey(category);
  const mapped = CATEGORY_BY_API[key];
  if (mapped) return mapped.label;
  // Accept either API enums or already-mapped mock labels.
  for (const entry of Object.values(CATEGORY_BY_API)) {
    if (entry.label.toLowerCase() === key) return entry.label;
  }
  return category.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** The mock's SHORT map: the abbreviation printed in the script margin. */
export function shortCategory(category: string): string {
  const key = categoryKey(category);
  const mapped = CATEGORY_BY_API[key];
  if (mapped) return mapped.short;
  for (const entry of Object.values(CATEGORY_BY_API)) {
    if (entry.label.toLowerCase() === key) return entry.short;
  }
  return key.split(/[\s&]+/)[0].slice(0, 8).toUpperCase();
}

export function humanizeStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Prefer the mock label when the category is known; else title-case snake_case. */
export function humanizeCategory(category: string): string {
  return displayCategory(category);
}

/**
 * Mock decision language for a clearance item. Never invents settlement —
 * zero-claim open items stay “Needs research”.
 */
export function displayStatus(item: {
  status: string;
  displayStatus?: string;
  disposition?: string;
  sourcesDisagree?: boolean;
  claimCount?: number;
  evidenceState?: { claimCount?: number };
}): string {
  if (item.displayStatus && item.displayStatus.trim().length > 0) {
    // API-provided display string still goes through sentence casing of known mocks.
    const known = knownStatusLabels().find(
      (label) => label.toLowerCase() === item.displayStatus!.toLowerCase(),
    );
    if (known) return known;
  }

  const status = item.status.toLowerCase();
  const disposition = (item.disposition ?? "").toLowerCase();
  const claimCount = item.claimCount ?? item.evidenceState?.claimCount ?? 0;

  if (status === "blocked" || disposition === "must_fix" || disposition === "blocked") {
    return "Must fix";
  }
  if (item.sourcesDisagree || status === "conflict" || disposition === "conflict") {
    return "Sources disagree";
  }
  if (status === "referred" || disposition === "referred") {
    return "With specialist";
  }
  if (SETTLED_STATUSES.has(status) || disposition === "verified" || disposition === "ruled_out") {
    return "Verified";
  }
  if (status === "could_not_verify" || disposition === "could_not_verify") {
    return "Could not verify";
  }
  if (claimCount === 0) {
    return "Needs research";
  }
  return "Needs your call";
}

function knownStatusLabels(): string[] {
  return [
    "Needs your call",
    "Sources disagree",
    "With specialist",
    "Verified",
    "Must fix",
    "Could not verify",
    "Needs research",
  ];
}

export function displayStatusTone(item: {
  status: string;
  displayStatus?: string;
  disposition?: string;
  sourcesDisagree?: boolean;
  claimCount?: number;
  evidenceState?: { claimCount?: number };
}): Tone {
  const label = displayStatus(item);
  if (label === "Verified") return "is-success";
  if (label === "Must fix") return "is-danger";
  if (label === "Sources disagree" || label === "With specialist" || label === "Needs your call") {
    return "is-warning";
  }
  return "";
}

/** Relative-or-absolute stamp matching the mock's fmtStamp spirit (simple form). */
export function formatStamp(iso: string | undefined | null): string {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const deltaMs = Date.now() - then.getTime();
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Truncate long provider excerpts without inventing meaning. */
export function clampExcerpt(text: string, max = 280): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (collapsed.length <= max) return collapsed;
  return `${collapsed.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Strip noisy markdown from Parallel extract dumps so the source table reads
 * like the mock's short claim cells rather than raw HTML/markdown soup.
 */
export function cleanExcerpt(text: string): string {
  return text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\|.*\|\s*$/gm, " ")
    .replace(/^[-*+]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function clampCleanExcerpt(text: string, max = 180): string {
  return clampExcerpt(cleanExcerpt(text), max);
}

/** Human bearing labels for the mock source table. */
export function bearingLabel(stance: string): string {
  const key = stance.toLowerCase();
  if (key === "supports" || key === "supporting" || key === "support") return "Supports";
  if (key === "conflicts" || key === "conflicting" || key === "conflict" || key === "opposing") {
    return "Disagrees";
  }
  return "Context";
}

export function bearingTone(stance: string): Tone {
  const label = bearingLabel(stance);
  if (label === "Supports") return "is-success";
  if (label === "Disagrees") return "is-danger";
  return "is-warning";
}

/** Human authority tier labels (mock vocabulary). */
export function authorityLabel(authority: string): string {
  const key = authority.toLowerCase().replace(/-/g, "_");
  if (key.includes("primary_registry") || key === "primary_registry") return "Primary registry";
  if (key.startsWith("primary")) return "Primary";
  if (key.includes("secondary")) return "Secondary";
  if (key.includes("policy")) return "Policy";
  if (key.includes("mixed")) return "Mixed";
  if (key.includes("unavailable")) return "Unavailable";
  return authority.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Mock revision stock for a version number (1-based). */
export function revisionStock(version: number | undefined | null): string {
  const stocks = ["white", "blue", "pink", "yellow", "green", "goldenrod"];
  if (!version || version < 1) return stocks[0]!;
  return stocks[(version - 1) % stocks.length]!;
}

export function revisionStockLabel(version: number | undefined | null): string {
  return `${revisionStock(version)} pages`;
}

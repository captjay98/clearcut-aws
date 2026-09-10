import { describe, expect, it } from "vitest";
import type { ClearanceItem } from "@clearcut/contracts";
import {
  authorityLabel,
  bearingLabel,
  clampExcerpt,
  displayCategory,
  displayStatus,
  revisionStock,
  shortCategory,
  severityWord,
} from "../itemPresentation";

function item(overrides: Partial<ClearanceItem> = {}): ClearanceItem {
  return {
    itemId: "01a00000-0000-7000-8000-000000000001",
    projectId: "01a00000-0000-7000-8000-000000000002",
    version: 1,
    category: "products_and_trademarks",
    entityName: "Coca-Cola",
    status: "unresolved",
    ...overrides,
  };
}

describe("displayCategory / shortCategory", () => {
  it("maps every API enum to the mock label and margin short", () => {
    expect(displayCategory("products_and_trademarks")).toBe("Brands & trademarks");
    expect(shortCategory("products_and_trademarks")).toBe("MARK");
    expect(displayCategory("locations_and_landmarks")).toBe("Locations & property");
    expect(shortCategory("locations_and_landmarks")).toBe("LOCATION");
    expect(displayCategory("corporate_entities")).toBe("Organizations & insignia");
    expect(shortCategory("corporate_entities")).toBe("INSIGNIA");
    expect(displayCategory("real_persons_living")).toBe("People & likeness");
    expect(displayCategory("music_and_lyrics")).toBe("Music & lyrics");
    expect(displayCategory("copyrighted_works")).toBe("Artwork & media");
    expect(displayCategory("vehicles_and_insignia")).toBe("Products & trade dress");
    expect(displayCategory("sensitive_historical_events")).toBe("Privacy & sensitive facts");
    expect(displayCategory("contact_information")).toBe("Dialogue & quotations");
  });
});

describe("displayStatus", () => {
  it("keeps zero-claim open items as Needs research", () => {
    expect(displayStatus(item({ claimCount: 0, status: "detected" }))).toBe("Needs research");
    expect(displayStatus(item({ claimCount: 0, status: "unresolved" }))).toBe("Needs research");
  });

  it("labels cited unresolved items as Needs your call", () => {
    expect(displayStatus(item({ claimCount: 6, status: "unresolved" }))).toBe("Needs your call");
  });

  it("surfaces source disagreement and blocks", () => {
    expect(displayStatus(item({ claimCount: 4, sourcesDisagree: true }))).toBe("Sources disagree");
    expect(displayStatus(item({ claimCount: 1, status: "blocked" }))).toBe("Must fix");
    expect(displayStatus(item({ claimCount: 1, status: "referred" }))).toBe("With specialist");
    expect(displayStatus(item({ claimCount: 1, status: "verified" }))).toBe("Verified");
  });
});

describe("severity and bearing", () => {
  it("derives severity words from API severity or status", () => {
    expect(severityWord(item({ severity: "High" }))).toBe("High");
    expect(severityWord(item({ status: "blocked" }))).toBe("High");
    expect(severityWord(item({ status: "unresolved", claimCount: 3 }))).toBe("Medium");
  });

  it("maps stance to mock bearing labels", () => {
    expect(bearingLabel("supports")).toBe("Supports");
    expect(bearingLabel("context")).toBe("Context");
    expect(bearingLabel("conflicts")).toBe("Disagrees");
    expect(bearingLabel("supporting")).toBe("Supports");
  });
});

describe("authority and excerpts", () => {
  it("humanizes authority tiers", () => {
    expect(authorityLabel("secondary_informal")).toBe("Secondary");
    expect(authorityLabel("primary_registry")).toBe("Primary registry");
  });

  it("clamps long provider dumps", () => {
    const long = "word ".repeat(200);
    const clamped = clampExcerpt(long, 40);
    expect(clamped.length).toBeLessThanOrEqual(40);
    expect(clamped.endsWith("…")).toBe(true);
  });
});

describe("revisionStock", () => {
  it("cycles mock stock colours by version", () => {
    expect(revisionStock(1)).toBe("white");
    expect(revisionStock(2)).toBe("blue");
    expect(revisionStock(7)).toBe("white");
  });
});

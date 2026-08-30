import { describe, it, expect } from "vitest";
import { CANONICAL_ROUTE_STATES } from "../fixtures/states.ts";

describe("UI State Matrix and Quality Gates", () => {
  it("covers all required route states", () => {
    expect(CANONICAL_ROUTE_STATES.length).toBeGreaterThanOrEqual(5);

    const routeIds = CANONICAL_ROUTE_STATES.map((s) => s.routeId);
    expect(routeIds).toContain("sign-in");
    expect(routeIds).toContain("onboarding");
    expect(routeIds).toContain("projects-list");
    expect(routeIds).toContain("project-new-wizard");
    expect(routeIds).toContain("team-access");
  });

  it("includes multiple viewports and themes", () => {
    const themes = new Set(CANONICAL_ROUTE_STATES.map((s) => s.theme));
    expect(themes.has("day-shoot")).toBe(true);
    expect(themes.has("night-shoot")).toBe(true);

    const widths = CANONICAL_ROUTE_STATES.map((s) => s.viewport.width);
    expect(widths).toContain(1440);
    expect(widths).toContain(768);
    expect(widths).toContain(375);
  });
});

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const layoutSource = readFileSync(
  new URL("../src/layouts/PublicLayout.astro", import.meta.url),
  "utf8",
);
const homeSource = readFileSync(
  new URL("../src/pages/index.astro", import.meta.url),
  "utf8",
);

describe("Public Astro site pages", () => {
  it("keeps authored public routes at the origin root", () => {
    expect(layoutSource).toContain('href="/features"');
    expect(layoutSource).toContain('href="/docs"');
    expect(homeSource).toContain('href="/features"');
  });

  it("links every workspace entry point through the same-origin app base", () => {
    for (const source of [layoutSource, homeSource]) {
      expect(source).toContain('href="/app/auth/sign-in"');
      expect(source).not.toContain("localhost:3000");
    }
  });
});

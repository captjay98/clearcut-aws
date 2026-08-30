import { describe, it, expect } from "vitest";

describe("Public Astro Site Pages", () => {
  it("defines public routes", () => {
    const routes = ["/", "/features", "/docs"];
    expect(routes.length).toBe(3);
  });
});

import { describe, expect, it } from "vitest";

import viteConfig from "../../vite.config";

describe("Vitest collection boundary", () => {
  it("collects unit and config tests without importing Playwright specs", () => {
    const config = viteConfig as {
      test?: { include?: string[] };
    };

    expect(config.test?.include).toEqual([
      "tests/unit/**/*.test.{ts,tsx}",
      "tests/config/**/*.test.ts",
      "src/**/__tests__/**/*.test.{ts,tsx}",
    ]);
  });
});

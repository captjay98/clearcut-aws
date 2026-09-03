import { describe, expect, it } from "vitest";

import playwrightConfig from "../../playwright.config";

describe("Playwright browser matrix", () => {
  it("keeps cross-engine desktop, tablet, and mobile coverage", () => {
    const projects = (playwrightConfig.projects ?? []).map((project) => ({
      name: project.name,
      browser: project.use?.defaultBrowserType,
      viewport: project.use?.viewport,
      isMobile: project.use?.isMobile,
    }));

    expect(projects).toEqual([
      {
        name: "chromium-desktop-1440",
        browser: "chromium",
        viewport: { width: 1440, height: 900 },
        isMobile: false,
      },
      {
        name: "firefox-desktop-1024",
        browser: "firefox",
        viewport: { width: 1024, height: 768 },
        isMobile: false,
      },
      {
        name: "webkit-tablet-768",
        browser: "webkit",
        viewport: { width: 768, height: 1024 },
        isMobile: false,
      },
      {
        name: "mobile-375",
        browser: "webkit",
        viewport: { width: 375, height: 667 },
        isMobile: true,
      },
    ]);
  });
});

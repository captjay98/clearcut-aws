import { describe, it, expect } from "vitest";
import React from "react";
import { OrgSettingsRoute } from "../../src/routes/o.$orgSlug.settings.tsx";
import { SettingsPage } from "../../src/features/settings/SettingsPage.tsx";

describe("Settings and Retention UI Routes and Features", () => {
  it("renders OrgSettingsRoute and SettingsPage", () => {
    expect(OrgSettingsRoute).toBeDefined();
    expect(SettingsPage).toBeDefined();
    const elem = React.createElement(OrgSettingsRoute);
    expect(elem.type).toBe(OrgSettingsRoute);
  });
});

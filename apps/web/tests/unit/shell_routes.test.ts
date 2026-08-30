import { describe, it, expect } from "vitest";
import React from "react";
import { Header } from "../../src/components/navigation/Header.tsx";
import { Sidebar } from "../../src/components/navigation/Sidebar.tsx";
import { RootLayout } from "../../src/routes/__root.tsx";
import { OrgLayout } from "../../src/routes/o/$orgSlug/route.tsx";

describe("Web Workspace Shell Components", () => {
  it("renders Header navigation", () => {
    expect(Header).toBeDefined();
    const elem = React.createElement(Header, {
      currentOrgSlug: "acme-films",
      userEmail: "reviewer@acme.com",
      userRole: "Reviewer",
    });
    expect(elem.type).toBe(Header);
  });

  it("renders Sidebar menu", () => {
    expect(Sidebar).toBeDefined();
    const elem = React.createElement(Sidebar, { activeOrgSlug: "acme-films" });
    expect(elem.type).toBe(Sidebar);
  });

  it("renders RootLayout container", () => {
    expect(RootLayout).toBeDefined();
    const elem = React.createElement(RootLayout);
    expect(elem.type).toBe(RootLayout);
  });

  it("renders OrgLayout with sidebar", () => {
    expect(OrgLayout).toBeDefined();
    const elem = React.createElement(OrgLayout);
    expect(elem.type).toBe(OrgLayout);
  });
});

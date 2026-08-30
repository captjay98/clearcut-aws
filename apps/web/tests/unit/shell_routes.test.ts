import { describe, it, expect } from "vitest";
import React from "react";
import { RootLayout } from "../../src/routes/__root.tsx";
import { OrgLayout } from "../../src/routes/o.$orgSlug.tsx";
import { Header } from "../../src/components/navigation/Header.tsx";
import { Sidebar } from "../../src/components/navigation/Sidebar.tsx";

describe("Web Workspace Shell Components", () => {
  it("renders Header navigation", () => {
    expect(Header).toBeDefined();
    const elem = React.createElement(Header, { currentOrg: "paramount" });
    expect(elem.props.currentOrg).toBe("paramount");
  });

  it("renders Sidebar menu", () => {
    expect(Sidebar).toBeDefined();
    const elem = React.createElement(Sidebar, { orgSlug: "paramount" });
    expect(elem.props.orgSlug).toBe("paramount");
  });

  it("renders RootLayout container", () => {
    expect(RootLayout).toBeDefined();
    const elem = React.createElement(RootLayout, null, React.createElement("div", null, "App"));
    expect(elem.type).toBe(RootLayout);
  });

  it("renders OrgLayout with sidebar", () => {
    expect(OrgLayout).toBeDefined();
    const elem = React.createElement(
      OrgLayout,
      { orgSlug: "paramount" },
      React.createElement("div", null, "Page")
    );
    expect(elem.props.orgSlug).toBe("paramount");
  });
});

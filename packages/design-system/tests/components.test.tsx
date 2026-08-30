import { describe, it, expect } from "vitest";
import React from "react";
import { Page } from "../src/components/Page.tsx";
import { Card } from "../src/components/Card.tsx";
import { Badge } from "../src/components/Badge.tsx";
import { Banner } from "../src/components/Banner.tsx";
import { StatGrid } from "../src/components/StatGrid.tsx";
import { Progress } from "../src/components/Progress.tsx";
import { Dialog } from "../src/adapters/dialog.tsx";
import { Combobox } from "../src/adapters/combobox.tsx";

describe("Design System Primitives and Adapters", () => {
  it("renders Page component structure", () => {
    expect(Page).toBeDefined();
    const elem = React.createElement(
      Page,
      {
        title: "Test Page",
        trail: [{ label: "Home", href: "/" }, { label: "Project" }],
      },
      React.createElement("div", null, "Content")
    );
    expect(elem.type).toBe(Page);
  });

  it("renders Card component", () => {
    expect(Card).toBeDefined();
    const elem = React.createElement(
      Card,
      { title: "Test Card" },
      React.createElement("p", null, "Card Body")
    );
    expect(elem.type).toBe(Card);
  });

  it("renders Badge variants", () => {
    expect(Badge).toBeDefined();
    const badge = React.createElement(Badge, {
      label: "Resolved",
      variant: "success",
    });
    expect(badge.props.label).toBe("Resolved");
  });

  it("renders Banner alert", () => {
    expect(Banner).toBeDefined();
    const banner = React.createElement(
      Banner,
      { type: "warning", title: "Notice" },
      "Sample Banner Content"
    );
    expect(banner.props.type).toBe("warning");
  });

  it("renders StatGrid metrics", () => {
    expect(StatGrid).toBeDefined();
    const grid = React.createElement(StatGrid, {
      stats: [
        { label: "Items", value: 42 },
        { label: "Flags", value: 5 },
      ],
    });
    expect(grid.props.stats.length).toBe(2);
  });

  it("renders Progress bar", () => {
    expect(Progress).toBeDefined();
    const prog = React.createElement(Progress, { value: 75, max: 100 });
    expect(prog.props.value).toBe(75);
  });

  it("renders Dialog adapter", () => {
    expect(Dialog).toBeDefined();
    const dialog = React.createElement(
      Dialog,
      { isOpen: true, onClose: () => {}, title: "Test Dialog" },
      "Dialog Content"
    );
    expect(dialog.props.isOpen).toBe(true);
  });

  it("renders Combobox adapter", () => {
    expect(Combobox).toBeDefined();
    const combo = React.createElement(Combobox, {
      options: [{ value: "1", label: "Option 1" }],
      onChange: () => {},
    });
    expect(combo.props.options.length).toBe(1);
  });
});

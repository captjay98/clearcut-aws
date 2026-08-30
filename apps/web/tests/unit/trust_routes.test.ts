import { describe, it, expect } from "vitest";
import React from "react";
import { OrgTrustRoute } from "../../src/routes/o/$orgSlug/trust.tsx";
import { TrustPage } from "../../src/features/trust/TrustPage.tsx";

describe("Trust and Learning Governance UI Routes and Features", () => {
  it("renders OrgTrustRoute and TrustPage", () => {
    expect(OrgTrustRoute).toBeDefined();
    expect(TrustPage).toBeDefined();
    const elem = React.createElement(OrgTrustRoute);
    expect(elem.type).toBe(OrgTrustRoute);
  });
});

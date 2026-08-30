import { describe, it, expect } from "vitest";
import React from "react";
import { OrgRecordsRoute } from "../../src/routes/o/$orgSlug/records.tsx";
import { RecordsPage } from "../../src/features/records/RecordsPage.tsx";

describe("Records UI Routes and Features", () => {
  it("renders OrgRecordsRoute and RecordsPage", () => {
    expect(OrgRecordsRoute).toBeDefined();
    expect(RecordsPage).toBeDefined();
    const elem = React.createElement(OrgRecordsRoute);
    expect(elem.type).toBe(OrgRecordsRoute);
  });
});

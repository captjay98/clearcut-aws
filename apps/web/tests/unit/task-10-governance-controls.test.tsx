// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ItemGovernanceControls } from "../../src/features/clearance/ItemGovernanceControls";

afterEach(cleanup);

describe("ItemGovernanceControls authoritative assignment", () => {
  it("preserves the assignee when the command is rejected", async () => {
    const onAssign = vi.fn(async () => {
      throw new Error("The assignment is stale.");
    });
    const user = userEvent.setup();

    render(
      <ItemGovernanceControls
        assignedTo={null}
        disposition={null}
        onAssign={onAssign}
      />,
    );

    const input = screen.getByLabelText("Assignee member ID");
    await user.type(input, "member-2");
    await user.click(screen.getByRole("button", { name: "Save Assignment" }));

    expect(onAssign).toHaveBeenCalledWith("member-2");
    expect((input as HTMLInputElement).value).toBe("member-2");
    expect(screen.getByRole("alert").textContent).toContain("stale");
  });
});



describe("ItemGovernanceControls authoritative disposition", () => {
  it("preserves the disposition rationale when the command is rejected", async () => {
    const onSetDisposition = vi.fn(async () => {
      throw new Error("The disposition is stale.");
    });
    const user = userEvent.setup();

    render(
      <ItemGovernanceControls
        assignedTo={null}
        disposition="pending"
        onSetDisposition={onSetDisposition}
      />,
    );

    const disposition = screen.getByLabelText("Disposition");
    const rationale = screen.getByLabelText("Disposition rationale");
    await user.selectOptions(disposition, "deferred");
    await user.type(rationale, "Qualified review is still required.");
    await user.click(screen.getByRole("button", { name: "Save Disposition" }));

    expect(onSetDisposition).toHaveBeenCalledWith(
      "deferred",
      "Qualified review is still required.",
    );
    expect((disposition as HTMLSelectElement).value).toBe("deferred");
    expect((rationale as HTMLTextAreaElement).value).toBe(
      "Qualified review is still required.",
    );
    expect(screen.getByRole("alert").textContent).toContain("stale");
  });
});

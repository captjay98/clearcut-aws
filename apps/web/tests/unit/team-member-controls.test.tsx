// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Membership } from "@clearcut/contracts";
import { TeamMemberControls } from "../../src/features/team/TeamMemberControls";

afterEach(cleanup);

function makeMember(overrides: Partial<Membership> = {}): Membership {
  return {
    membershipId: "m-1",
    orgId: "org-1",
    userId: "user-1",
    email: "colleague@studio.com",
    role: "reviewer",
    active: true,
    projectGrants: [],
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("TeamMemberControls gating", () => {
  it("hides governed controls when the caller cannot manage", () => {
    render(<TeamMemberControls member={makeMember()} canManage={false} />);

    expect(screen.queryByRole("button", { name: "Change Role" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Deactivate" })).toBeNull();
    expect(screen.getByText(/require an owner or admin/i)).toBeTruthy();
  });
});

describe("TeamMemberControls role change", () => {
  it("calls onChangeRole with the selected role", async () => {
    const onChangeRole = vi.fn(async () => {});
    const user = userEvent.setup();

    render(
      <TeamMemberControls
        member={makeMember({ role: "reviewer" })}
        canManage
        onChangeRole={onChangeRole}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Role"), "admin");
    await user.click(screen.getByRole("button", { name: "Change Role" }));

    expect(onChangeRole).toHaveBeenCalledWith("admin");
  });

  it("surfaces the rejection message and keeps the selected role", async () => {
    const onChangeRole = vi.fn(async () => {
      throw new Error("The membership changed underneath us.");
    });
    const user = userEvent.setup();

    render(
      <TeamMemberControls
        member={makeMember({ role: "reviewer" })}
        canManage
        onChangeRole={onChangeRole}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Role"), "editor");
    await user.click(screen.getByRole("button", { name: "Change Role" }));

    expect((screen.getByLabelText("Role") as HTMLSelectElement).value).toBe("editor");
    expect(screen.getByRole("alert").textContent).toContain("changed underneath");
  });
});

describe("TeamMemberControls project grants", () => {
  it("parses comma-separated ids into an array", async () => {
    const onChangeProjectGrant = vi.fn(async () => {});
    const user = userEvent.setup();

    render(
      <TeamMemberControls
        member={makeMember()}
        canManage
        onChangeProjectGrant={onChangeProjectGrant}
      />,
    );

    await user.type(
      screen.getByLabelText("Project grants (comma-separated IDs)"),
      "proj-a, proj-b ",
    );
    await user.click(screen.getByRole("button", { name: "Change Grants" }));

    expect(onChangeProjectGrant).toHaveBeenCalledWith(["proj-a", "proj-b"]);
  });
});

describe("TeamMemberControls activation", () => {
  it("deactivates an active member", async () => {
    const onDeactivate = vi.fn(async () => {});
    const user = userEvent.setup();

    render(
      <TeamMemberControls
        member={makeMember({ active: true })}
        canManage
        onDeactivate={onDeactivate}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(onDeactivate).toHaveBeenCalledTimes(1);
  });

  it("reactivates an inactive member", async () => {
    const onReactivate = vi.fn(async () => {});
    const user = userEvent.setup();

    render(
      <TeamMemberControls
        member={makeMember({ active: false })}
        canManage
        onReactivate={onReactivate}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Reactivate" }));
    expect(onReactivate).toHaveBeenCalledTimes(1);
  });
});

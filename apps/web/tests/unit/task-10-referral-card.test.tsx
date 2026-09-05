// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReferralCard } from "../../src/features/collaboration/ReferralCard";

afterEach(cleanup);

describe("ReferralCard authoritative submission", () => {
  it("preserves referral inputs when a stale conflict rejects the command", async () => {
    const onRefer = vi.fn(async () => {
      throw Object.assign(new Error("The item changed during referral."), {
        code: "conflict_stale_version",
        retryable: false,
      });
    });
    const user = userEvent.setup();

    render(<ReferralCard itemId="item-1" referrals={[]} onRefer={onRefer} />);
    const question = screen.getByLabelText("Referral question");
    const rationale = screen.getByLabelText("Accountable rationale");
    await user.type(question, "Does this source resolve the identity conflict?");
    await user.type(rationale, "A specialist must assess the cited record.");
    await user.click(screen.getByRole("button", { name: "Send Formal Referral" }));

    expect((question as HTMLTextAreaElement).value).toBe(
      "Does this source resolve the identity conflict?",
    );
    expect((rationale as HTMLTextAreaElement).value).toBe(
      "A specialist must assess the cited record.",
    );
    expect(screen.getByRole("alert").textContent).toContain("item changed");
  });
});



describe("ReferralCard authoritative acknowledgement", () => {
  it("preserves acknowledgement inputs when the persisted command is rejected", async () => {
    const onAcknowledge = vi.fn(async () => {
      throw new Error("The referral acknowledgement is stale.");
    });
    const user = userEvent.setup();

    render(
      <ReferralCard
        itemId="item-1"
        referrals={[
          {
            referralId: "referral-1",
            targetRole: "reviewer",
            question: "Does the record resolve the identity conflict?",
            status: "submitted",
            submittedByActorId: "actor-1",
            submittedAt: "2026-09-06T00:00:00Z",
          },
        ]}
        onAcknowledge={onAcknowledge}
      />,
    );

    const response = screen.getByLabelText("Referral response");
    const rationale = screen.getByLabelText("Acknowledgement rationale");
    await user.type(response, "The source identifies a different entity.");
    await user.type(rationale, "The conflict must remain unresolved.");
    await user.click(screen.getByRole("button", { name: "Acknowledge Referral" }));

    expect(onAcknowledge).toHaveBeenCalledWith(
      "referral-1",
      "The source identifies a different entity.",
      "The conflict must remain unresolved.",
    );
    expect((response as HTMLTextAreaElement).value).toBe(
      "The source identifies a different entity.",
    );
    expect((rationale as HTMLTextAreaElement).value).toBe(
      "The conflict must remain unresolved.",
    );
    expect(screen.getByRole("alert").textContent).toContain("stale");
  });
});

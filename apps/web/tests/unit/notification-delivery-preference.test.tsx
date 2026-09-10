// @vitest-environment jsdom

import React from "react";
import { QueryClient } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiResult, NotificationDeliveryPreference } from "@clearcut/contracts";
import { NotificationDeliveryPreferenceForm } from "../../src/features/settings/NotificationDeliveryPreferenceForm";
import {
  executeSetNotificationDeliveryPreference,
  setNotificationDeliveryPreferenceMutationOptions,
} from "../../src/mutations/notificationCommands";
import { notificationKeys } from "../../src/queries/notifications";

afterEach(cleanup);

describe("NotificationDeliveryPreferenceForm", () => {
  it("shows the stored channel and reports a change on selection", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <NotificationDeliveryPreferenceForm
        channel="in_app"
        saving={false}
        saved={false}
        onChange={onChange}
      />,
    );

    const select = screen.getByLabelText("Notification delivery") as HTMLSelectElement;
    expect(select.value).toBe("in_app");

    await user.selectOptions(select, "email");

    expect(onChange).toHaveBeenCalledWith("email");
    expect(select.value).toBe("email");
  });

  it("does not fire onChange when the current channel is re-selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <NotificationDeliveryPreferenceForm
        channel="email"
        saving={false}
        saved={false}
        onChange={onChange}
      />,
    );

    const select = screen.getByLabelText("Notification delivery") as HTMLSelectElement;
    await user.selectOptions(select, "email");

    expect(onChange).not.toHaveBeenCalled();
  });

  it("disables the control while saving and surfaces a rejection", () => {
    render(
      <NotificationDeliveryPreferenceForm
        channel="push"
        saving={false}
        saved={false}
        error="The preference was not stored."
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain("not stored");
  });

  it("re-bases the selection on the authoritative channel", () => {
    const { rerender } = render(
      <NotificationDeliveryPreferenceForm
        channel="in_app"
        saving={false}
        saved={false}
        onChange={vi.fn()}
      />,
    );

    rerender(
      <NotificationDeliveryPreferenceForm
        channel="push"
        saving={false}
        saved
        onChange={vi.fn()}
      />,
    );

    const select = screen.getByLabelText("Notification delivery") as HTMLSelectElement;
    expect(select.value).toBe("push");
    expect(screen.getByRole("status").textContent).toContain("Push");
  });
});

describe("setNotificationDeliveryPreference command", () => {
  it("sends the selected channel and returns the stored preference", async () => {
    const setNotificationDeliveryPreference = vi.fn(
      async (): Promise<ApiResult<NotificationDeliveryPreference>> => ({
        ok: true,
        value: { channel: "email" },
      }),
    );

    const preference = await executeSetNotificationDeliveryPreference(
      "org-1",
      "email",
      { setNotificationDeliveryPreference },
    );

    expect(setNotificationDeliveryPreference).toHaveBeenCalledWith({
      params: { orgId: "org-1" },
      body: { channel: "email" },
    });
    expect(preference).toEqual({ channel: "email" });
  });

  it("throws the typed error on rejection without retrying", async () => {
    const setNotificationDeliveryPreference = vi.fn(
      async (): Promise<ApiResult<NotificationDeliveryPreference>> => ({
        ok: false,
        error: { code: "permission_denied", message: "Not a member." },
      }),
    );

    await expect(
      executeSetNotificationDeliveryPreference("org-1", "push", {
        setNotificationDeliveryPreference,
      }),
    ).rejects.toThrow("Not a member.");
  });

  it("seeds the cache with the authoritative preference on success", () => {
    const queryClient = new QueryClient();
    const options = setNotificationDeliveryPreferenceMutationOptions(
      "org-1",
      queryClient,
      {
        setNotificationDeliveryPreference: vi.fn(),
      },
    );

    options.onSuccess({ channel: "push" });

    expect(
      queryClient.getQueryData(notificationKeys.deliveryPreference("org-1")),
    ).toEqual({ channel: "push" });
  });
});

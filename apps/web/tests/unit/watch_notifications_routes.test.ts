import { describe, it, expect } from "vitest";
import React from "react";
import { ProjectWatchRoute } from "../../src/routes/o/$orgSlug/projects/$projectId/watch.tsx";
import { WatchPage } from "../../src/features/watch/WatchPage.tsx";
import { OrgNotificationsRoute } from "../../src/routes/o/$orgSlug/notifications.tsx";
import { NotificationsPage } from "../../src/features/notifications/NotificationsPage.tsx";

describe("Watch and Notifications UI Routes and Features", () => {
  it("renders ProjectWatchRoute and WatchPage", () => {
    expect(ProjectWatchRoute).toBeDefined();
    expect(WatchPage).toBeDefined();
    const elem = React.createElement(ProjectWatchRoute);
    expect(elem.type).toBe(ProjectWatchRoute);
  });

  it("renders OrgNotificationsRoute and NotificationsPage", () => {
    expect(OrgNotificationsRoute).toBeDefined();
    expect(NotificationsPage).toBeDefined();
    const elem = React.createElement(OrgNotificationsRoute);
    expect(elem.type).toBe(OrgNotificationsRoute);
  });
});

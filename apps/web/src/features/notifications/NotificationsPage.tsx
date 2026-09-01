import React, { useState } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export interface NotificationItem {
  id: string;
  tier: "urgent" | "standard" | "informational";
  title: string;
  body?: string;
  message?: string;
  time?: string;
  createdAt?: string;
  read?: boolean;
}

export function NotificationsPage({
  notifications = [],
}: {
  notifications?: NotificationItem[];
}) {
  const [filterTier, setFilterTier] = useState<string>("all");

  const displayList = notifications ?? [];

  const filtered =
    filterTier === "all"
      ? displayList
      : displayList.filter((n) => n.tier === filterTier);

  return (
    <Page
      title="Notification Inbox"
      subtitle="Authorized alerts, mentions, review assignments, and source change updates"
      trail={[{ label: "Notifications" }]}
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {["all", "urgent", "standard", "informational"].map((t) => (
              <button
                key={t}
                onClick={() => setFilterTier(t)}
                className={`px-3 py-1 text-xs rounded-full capitalize font-medium ${
                  filterTier === t
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            Mark all as read
          </button>
        </div>

        <Card>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {filtered.length === 0 && (
              <div className="p-3 text-xs text-slate-500 dark:text-slate-400">
                No notifications.
              </div>
            )}
            {filtered.map((n) => (
              <div
                key={n.id}
                className={`p-3 text-xs flex items-start justify-between ${
                  !n.read ? "bg-blue-50/30 dark:bg-blue-950/20" : ""
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-slate-900 dark:text-white">{n.title}</span>
                    <Badge
                      label={n.tier}
                      variant={n.tier === "urgent" ? "danger" : "primary"}
                    />
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{n.body || n.message}</p>
                </div>
                <span className="text-[11px] text-slate-400">{n.time || n.createdAt || "Just now"}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}

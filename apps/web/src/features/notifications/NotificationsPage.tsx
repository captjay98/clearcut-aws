import React, { useState } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export function NotificationsPage() {
  const [filterTier, setFilterTier] = useState<string>("all");

  const sampleNotifications = [
    {
      id: "n1",
      tier: "urgent",
      title: "Material source change detected",
      body: "A monitored trademark source was flagged for material change.",
      time: "5 mins ago",
      read: false,
    },
    {
      id: "n2",
      tier: "standard",
      title: "Evidence decision recorded",
      body: "Sarah recorded 'Accept as-is' on Scene 1 item.",
      time: "1 hour ago",
      read: true,
    },
  ];

  const filtered =
    filterTier === "all"
      ? sampleNotifications
      : sampleNotifications.filter((n) => n.tier === filterTier);

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
                  <p className="text-slate-600 dark:text-slate-400">{n.body}</p>
                </div>
                <span className="text-[11px] text-slate-400">{n.time}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}

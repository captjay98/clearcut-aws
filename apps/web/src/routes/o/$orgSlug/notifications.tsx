import React, { useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";

export const Route = createFileRoute("/o/$orgSlug/notifications")({
  component: OrgNotificationsRoute,
});

export function OrgNotificationsRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/notifications" });
  const [notifications] = useState<any[]>([]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Notifications</h1>
        <p className="text-sm text-slate-400">
          Clearance task assignments, referrals, and monitoring alerts.
        </p>
      </div>

      <div className="p-8 bg-slate-900 border border-slate-800 rounded-lg text-center text-xs text-slate-500">
        No unread notifications for {orgSlug}.
      </div>
    </div>
  );
}

export default OrgNotificationsRoute;

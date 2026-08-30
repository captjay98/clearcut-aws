import React, { useState, useEffect } from "react";
import { NotificationsPage } from "../../../features/notifications/NotificationsPage.tsx";
import { loadNotifications } from "../../../lib/loaders.ts";

export function OrgNotificationsRoute({ params }: { params?: { orgSlug: string } }) {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    loadNotifications(params?.orgSlug || "acme-films").then(setData);
  }, [params?.orgSlug]);

  return <NotificationsPage />;
}

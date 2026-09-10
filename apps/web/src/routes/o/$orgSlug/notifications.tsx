import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type Notification } from "@clearcut/contracts";
import { Badge, Banner, EmptyState, Page, Section, TabsBar } from "../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/notifications")({
  component: OrgNotificationsRoute,
});

export function OrgNotificationsRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/notifications" });
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("unread");
  const [marking, setMarking] = useState(false);

  // This surface previously rendered a hardcoded "no unread notifications"
  // without ever asking the server, which asserted an empty inbox it had not
  // checked. It now reads the authoritative list and says so when it cannot.
  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listNotifications({ params: { orgId: orgSlug } });
      if (result.ok) {
        setNotifications(result.value ?? []);
      } else {
        setNotifications([]);
        setError(result.error.message);
      }
    } catch {
      setNotifications([]);
      setError("Notifications could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await load();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const unread = notifications.filter((notification) => !notification.read);
  const visible = filter === "unread" ? unread : notifications;

  async function markAllRead() {
    setMarking(true);
    try {
      const result = await api.markAllNotificationsRead({ params: { orgId: orgSlug } });
      if (result.ok) {
        await load();
      } else {
        setError(result.error.message);
      }
    } finally {
      setMarking(false);
    }
  }

  async function markOneRead(notificationId: string) {
    const result = await api.markNotificationRead({
      params: { orgId: orgSlug, notificationId },
    });
    if (result.ok) {
      await load();
    } else {
      setError(result.error.message);
    }
  }

  return (
    <Page
      trail={[{ label: "Notifications" }]}
      eyebrow="Inbox"
      title="Notifications"
      lede="Clearance task assignments, referrals, and monitoring alerts."
      notice={
        error && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Notifications unavailable"
            message={`${error} No empty-inbox conclusion has been inferred.`}
            role="alert"
          />
        )
      }
    >
      {loading ? (
        <p role="status" className="small muted">
          Loading notifications…
        </p>
      ) : error ? null : (
        <>
          <TabsBar
            items={[
              { value: "unread", label: "Unread", count: unread.length },
              { value: "all", label: "All", count: notifications.length },
            ]}
            active={filter}
            onChange={setFilter}
            label="Filter notifications"
          />

          {unread.length > 0 && (
            <div className="row gap-t-2" style={{ justifyContent: "flex-end" }}>
              <button
                type="button"
                className="button button-secondary button-sm"
                onClick={() => void markAllRead()}
                disabled={marking}
              >
                {marking ? "Marking…" : `Mark all as read (${unread.length})`}
              </button>
            </div>
          )}

          <Section>
            {visible.length === 0 ? (
              <EmptyState
                icon="◔"
                title={filter === "unread" ? "Nothing unread" : "Nothing yet"}
                description={
                  filter === "unread"
                    ? "Every notification in this organization has been read."
                    : "Assignments, referrals, and monitoring alerts appear here."
                }
              />
            ) : (
              <div className="list">
                {visible.map((notification) => (
                  <div
                    className={`list-row is-static ${notification.read ? "" : "is-row-accent"}`.trim()}
                    key={notification.notificationId}
                  >
                    <div className="list-main">
                      <span className="list-title">{notification.title}</span>
                      <span className="list-meta">
                        <span>{notification.body}</span>
                        <span>{new Date(notification.createdAt).toLocaleString()}</span>
                      </span>
                    </div>
                    <div className="list-aside">
                      {notification.read ? (
                        <Badge>Read</Badge>
                      ) : (
                        <>
                          <Badge tone="is-accent">Unread</Badge>
                          <button
                            type="button"
                            className="button button-ghost button-sm"
                            onClick={() => void markOneRead(notification.notificationId)}
                          >
                            Mark read
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </Page>
  );
}

export default OrgNotificationsRoute;

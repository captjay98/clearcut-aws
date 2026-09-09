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

  // This surface previously rendered a hardcoded "no unread notifications"
  // without ever asking the server, which asserted an empty inbox it had not
  // checked. It now reads the authoritative list and says so when it cannot.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await api.listNotifications({ params: { orgId: orgSlug } });
        if (cancelled) {
          return;
        }
        if (result.ok) {
          setNotifications(result.value ?? []);
        } else {
          setNotifications([]);
          setError(result.error.message);
        }
      } catch {
        if (!cancelled) {
          setNotifications([]);
          setError("Notifications could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();

    return () => {
      cancelled = true;
    };
  }, [orgSlug]);

  const unread = notifications.filter((notification) => !notification.read);
  const visible = filter === "unread" ? unread : notifications;

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
                      {notification.read ? <Badge>Read</Badge> : <Badge tone="is-accent">Unread</Badge>}
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

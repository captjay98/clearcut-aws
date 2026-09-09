import React, { useState } from "react";
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { PublicShell } from "../../../components/shell/PublicShell";
import { Banner, Card } from "../../../components/ds";

export const Route = createFileRoute("/auth/invite/$token")({
  component: AcceptInviteRoute,
});

export function AcceptInviteRoute() {
  const { token } = useParams({ from: "/auth/invite/$token" });
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAccept = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await api.acceptInvitation({ params: { token } });
      if (!res.ok) {
        setError(res.error.message || "Failed to accept invitation");
        return;
      }

      // Route to whichever organization the server resolves for this account.
      // This previously navigated to a hardcoded "northlight" slug, so anyone
      // accepting an invitation landed on an organization they may not belong to.
      const entry = await api.resolveOrganizationEntry();
      if (entry.ok && entry.value.defaultOrgSlug) {
        navigate({ to: "/o/$orgSlug/projects", params: { orgSlug: entry.value.defaultOrgSlug } });
        return;
      }
      setError(
        "The invitation was accepted, but no workspace could be resolved for this account. Sign in to continue.",
      );
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PublicShell
      eyebrow="Invitation"
      title="Team Invitation"
      lede="You have been invited to join a ClearCut screenplay pre-clearance workspace. Your role is fixed by the invitation and enforced by the server."
    >
      <div>
        {error && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not accept the invitation"
            message={error}
            role="alert"
            className="gap-b-6"
          />
        )}

        <Card accent>
          <div className="cluster">
            <button
              className="button button-primary"
              type="button"
              onClick={handleAccept}
              disabled={loading}
            >
              {loading ? "Accepting…" : "Accept Invitation & Open Workspace"}
            </button>
          </div>
        </Card>
      </div>
    </PublicShell>
  );
}

export default AcceptInviteRoute;

import React, { useEffect, useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { api, type Organization } from "@clearcut/contracts";
import { PublicShell } from "../components/shell/PublicShell";

export const Route = createFileRoute("/organizations")({
  component: OrganizationsRoute,
});

/**
 * Mock's "Choose an organization" resolver. Shown when the signed-in account
 * belongs to more than one organization; single-org accounts skip straight to
 * their default workspace.
 */
export function OrganizationsRoute() {
  const navigate = useNavigate();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const session = await api.getSessionContext();
      if (!session.ok || !session.value.authenticated) {
        if (!cancelled) navigate({ to: "/auth/sign-in" });
        return;
      }
      const result = await api.listOrganizations();
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error.message);
        setOrgs([]);
        return;
      }
      if (result.value.length === 0) {
        navigate({ to: "/onboarding" });
        return;
      }
      if (result.value.length === 1) {
        navigate({
          to: "/o/$orgSlug/projects",
          params: { orgSlug: result.value[0]!.slug },
        });
        return;
      }
      setOrgs(result.value);
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <PublicShell
      eyebrow="Workspace"
      title="Choose an organization"
      lede="This account belongs to more than one organization. Pick the workspace you want to open."
    >
      {error && (
        <div className="banner is-danger gap-b-4" role="alert">
          <span className="banner-icon" aria-hidden="true">
            ⚠
          </span>
          <span className="banner-body">{error}</span>
        </div>
      )}
      {orgs === null && !error ? (
        <p role="status" className="small muted">
          Loading organizations…
        </p>
      ) : (
        <ul className="list" aria-label="Organizations">
          {(orgs ?? []).map((org) => (
            <li key={org.orgId} className="list-row is-static">
              <div className="list-main">
                <Link
                  className="list-title"
                  to="/o/$orgSlug/projects"
                  params={{ orgSlug: org.slug }}
                >
                  {org.name}
                </Link>
                <span className="list-meta">
                  <span className="mono small">{org.slug}</span>
                </span>
              </div>
              <div className="list-aside">
                <Link
                  className="button button-primary button-sm"
                  to="/o/$orgSlug/projects"
                  params={{ orgSlug: org.slug }}
                >
                  Open
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </PublicShell>
  );
}

export default OrganizationsRoute;

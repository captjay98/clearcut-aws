import React, { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { PublicShell } from "../components/shell/PublicShell";
import { Banner, Card, DataTable, Section } from "../components/ds";

export const Route = createFileRoute("/onboarding")({
  component: OnboardingRoute,
});

/**
 * The five fixed roles, mirroring ROLE_MATRIX in the canonical mock. Shown
 * during onboarding because review authority is decided here and the roles are
 * not configurable afterwards.
 */
const ROLE_MATRIX: readonly (readonly [string, string])[] = [
  ["Owner", "Billing, policy, release, all decisions"],
  ["Admin", "Team, providers, projects, all decisions"],
  ["Editor", "Import scripts, run research, propose rewrites"],
  ["Reviewer", "Verify sources, refer, record final decisions"],
  ["Viewer", "Read records and exports"],
];

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function OnboardingRoute() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleNameChange = (value: string) => {
    setName(value);
    setSlug(slugify(value));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await api.createOrganization({ body: { name, slug } });

      if (!res.ok) {
        setError(res.error.message || "Could not create organization.");
        return;
      }

      navigate({ to: "/o/$orgSlug/projects", params: { orgSlug: slug } });
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PublicShell
      eyebrow="Step 1 of 1"
      title="Create Workspace"
      lede="An organization owns projects, members, policies, and exports. Roles are fixed so review authority stays legible."
    >
      {error && (
        <Banner
          tone="is-danger"
          icon="⚠"
          title="Could not create the organization"
          message={error}
          role="alert"
          className="gap-b-6"
        />
      )}

      <form onSubmit={handleCreate}>
        <Card>
          <div className="form-grid">
            <label className="field field-full" htmlFor="org-name">
              <span className="field-label">Organization Name</span>
              <input
                id="org-name"
                type="text"
                required
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="Indie Film Studio"
              />
            </label>
            <label className="field field-full" htmlFor="org-slug">
              <span className="field-label">Workspace URL Identifier</span>
              <input
                id="org-slug"
                type="text"
                required
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                aria-describedby="org-slug-hint"
              />
              <span className="field-hint" id="org-slug-hint">
                Used in this workspace's address. Derived from the name, and editable.
              </span>
            </label>
          </div>
        </Card>

        <Section
          title="Fixed roles"
          description="Five roles instead of custom permission combinations."
        >
          <DataTable
            caption="The five fixed organization roles and their permissions"
            columns={[{ label: "Role" }, { label: "Permissions" }]}
            rows={ROLE_MATRIX.map(([role, can]) => [
              <strong key={role}>{role}</strong>,
              <span className="small muted" key={`${role}-can`}>
                {can}
              </span>,
            ])}
          />
        </Section>

        <div className="cluster gap-t-8">
          <button className="button button-primary" type="submit" disabled={loading}>
            {loading ? "Creating organization…" : "Create Organization"}
          </button>
        </div>
      </form>
    </PublicShell>
  );
}

export default OnboardingRoute;

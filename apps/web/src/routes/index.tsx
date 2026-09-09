import React from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/")({
  beforeLoad: async () => {
    const sessionRes = await api.getSessionContext();
    if (sessionRes.ok && sessionRes.value.authenticated) {
      const entryRes = await api.resolveOrganizationEntry();
      if (entryRes.ok && entryRes.value.defaultOrgSlug) {
        throw redirect({
          to: "/o/$orgSlug",
          params: { orgSlug: entryRes.value.defaultOrgSlug },
        });
      }
      throw redirect({ to: "/onboarding" });
    }
    throw redirect({ to: "/auth/sign-in" });
  },
  component: IndexPage,
});

/**
 * Only rendered if the redirect above does not fire, which should not happen in
 * practice. Kept minimal and landmark-free: the shell owns the main landmark.
 */
export function IndexPage() {
  return (
    <div className="page narrow">
      <header className="page-head">
        <h1 id="route-heading" tabIndex={-1}>
          ClearCut Workspace
        </h1>
        <p className="page-lede">Screenplay pre-clearance evidence desk.</p>
      </header>
    </div>
  );
}

export default IndexPage;

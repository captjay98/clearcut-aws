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

export function IndexPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold">ClearCut Workspace</h1>
      <p className="text-slate-400">Screenplay pre-clearance research desk</p>
    </main>
  );
}

export default IndexPage;

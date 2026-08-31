import React from "react";
import { createFileRoute, Outlet, useParams } from "@tanstack/react-router";
import { AppShell } from "../../../components/shell/AppShell";

export const Route = createFileRoute("/o/$orgSlug")({
  component: OrgLayout,
});

export function OrgLayout() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug" });
  return (
    <AppShell orgSlug={orgSlug}>
      <Outlet />
    </AppShell>
  );
}

export default OrgLayout;

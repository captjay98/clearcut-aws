import React, { useEffect } from "react";
import { createFileRoute, Outlet, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { useShell } from "../../../../../components/shell/ShellContext";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId")({
  component: ProjectLayout,
});

export function ProjectLayout() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId" });
  const { setProjectTitle } = useShell();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await api.getProject({ params: { orgId: orgSlug, projectId } });
        if (!cancelled && res.ok && res.value) {
          setProjectTitle(res.value.title);
        }
      } catch {
        // The chip falls back to a neutral label rather than inventing a title.
      }
    }
    load();

    return () => {
      cancelled = true;
      setProjectTitle(null);
    };
  }, [orgSlug, projectId, setProjectTitle]);

  // Project navigation lives in the shell's rail, matching the mock, which swaps
  // the rail from organization to project links rather than stacking a second
  // tab strip beneath the header.
  return <Outlet />;
}

export default ProjectLayout;

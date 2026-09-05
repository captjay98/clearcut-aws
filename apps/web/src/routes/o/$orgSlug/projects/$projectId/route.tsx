import React, { useEffect, useState } from "react";
import { createFileRoute, Link, Outlet, useParams, useRouterState } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId")({
  component: ProjectLayout,
});

export function ProjectLayout() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId" });
  const [projectTitle, setProjectTitle] = useState("Borrowed Light");
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getProject({ params: { orgId: orgSlug, projectId } });
        if (res.ok && res.value) {
          setProjectTitle(res.value.title);
        }
      } catch {
        // keep fallback
      }
    }
    load();
  }, [orgSlug, projectId]);

  const tabs = [
    { label: "Workspace", to: "/o/$orgSlug/projects/$projectId/workspace", active: currentPath.includes("/workspace") },
    { label: "Versions", to: "/o/$orgSlug/projects/$projectId/versions", active: currentPath.includes("/versions") },
    { label: "Clearance Report", to: "/o/$orgSlug/projects/$projectId/report", active: currentPath.includes("/report") },
    { label: "Watch & Monitor", to: "/o/$orgSlug/projects/$projectId/watch", active: currentPath.includes("/watch") },
  ];

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Project Tab Navigation Bar */}
      <div className="flex items-center space-x-1 border-b border-slate-800 pb-2">
        {tabs.map((tab) => (
          <Link
            key={tab.label}
            to={tab.to}
            params={{ orgSlug, projectId }}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500 ${
              tab.active
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </div>

      {/* Project View Content */}
      <div className="flex-1 min-h-0 flex flex-col">
        <Outlet />
      </div>
    </div>
  );
}

export default ProjectLayout;

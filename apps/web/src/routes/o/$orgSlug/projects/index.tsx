import React, { useEffect, useState } from "react";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/")({
  component: ProjectsListRoute,
});

export function ProjectsListRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/projects/" });
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await api.listProjects({ params: { orgId: orgSlug } });
        if (res.ok) {
          setProjects(res.value || []);
        } else {
          setError(res.error.message || "Failed to load projects");
        }
      } catch {
        setError("Network error while loading projects");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [orgSlug]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Clearance Projects</h1>
          <p className="text-sm text-slate-400">
            Active screenplay pre-clearance workspaces in this organization.
          </p>
        </div>
        <Link
          to="/o/$orgSlug/projects/new"
          params={{ orgSlug }}
          className="inline-flex items-center space-x-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          <span>+ New Project</span>
        </Link>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-950/50 border border-red-900 rounded-md text-sm text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-slate-500">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-slate-800 rounded-lg bg-slate-900/20">
          <div className="text-3xl mb-2">📁</div>
          <h3 className="text-base font-semibold text-slate-200">No clearance projects yet</h3>
          <p className="text-sm text-slate-400 mt-1 mb-4">
            Upload your first screenplay PDF or FDX file to get started.
          </p>
          <Link
            to="/o/$orgSlug/projects/new"
            params={{ orgSlug }}
            className="inline-flex items-center px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-md"
          >
            Create Project
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <Link
              key={p.projectId}
              to="/o/$orgSlug/projects/$projectId/workspace"
              params={{ orgSlug, projectId: p.projectId }}
              className="p-5 bg-slate-900/80 border border-slate-800 hover:border-amber-500/50 rounded-lg shadow-sm transition-all flex flex-col justify-between group focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <div>
                <h3 className="text-base font-bold text-slate-100 group-hover:text-amber-400 transition-colors">
                  {p.title}
                </h3>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                  {p.description || "No description provided."}
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
                <span>Created {new Date(p.createdAt).toLocaleDateString()}</span>
                <span className="text-amber-500 font-medium">Open Workspace →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default ProjectsListRoute;

import React, { useState } from "react";

interface ProjectItem {
  projectId: string;
  title: string;
  description?: string;
  createdAt: string;
}

interface ProjectsRouteProps {
  orgSlug: string;
  initialProjects?: ProjectItem[];
  userRole?: string;
}

export function OrgProjectsRoute({ orgSlug, initialProjects = [], userRole = "reviewer" }: ProjectsRouteProps) {
  const [projects] = useState<ProjectItem[]>(initialProjects);
  const canCreate = userRole === "owner" || userRole === "admin";

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Clearance Projects</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Workspace: {orgSlug}</p>
        </div>

        {canCreate && (
          <button
            type="button"
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
          >
            New Project
          </button>
        )}
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-lg">
          <h3 className="text-lg font-medium text-slate-900 dark:text-white mb-2">No projects yet</h3>
          <p className="text-sm text-slate-500 max-w-sm mx-auto mb-4">
            Upload your first screenplay to begin automated pre-clearance item detection and source research.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((p) => (
            <div
              key={p.projectId}
              className="p-6 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm"
            >
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">{p.title}</h2>
              {p.description && <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">{p.description}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

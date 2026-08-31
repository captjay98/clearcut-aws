import React, { useState } from "react";
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/new")({
  component: NewProjectRoute,
});

export function NewProjectRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/projects/new" });
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await api.createProject({
        path: { org_id: orgSlug },
        body: { title, description },
      });

      if (!res.ok) {
        setError(res.error.message || "Failed to create project");
        return;
      }

      const projId = res.value.data.projectId;
      navigate({
        to: "/o/$orgSlug/projects/$projectId/workspace",
        params: { orgSlug, projectId: projId },
      });
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto py-8">
      <div className="card p-6 bg-slate-900 border border-slate-800 rounded-lg shadow">
        <h1 className="text-xl font-bold text-white mb-1">New Clearance Project</h1>
        <p className="text-xs text-slate-400 mb-6">
          Set up a new screenplay workspace for automated detection and research.
        </p>

        {error && (
          <div role="alert" className="mb-4 p-3 bg-red-950/50 border border-red-900 rounded text-xs text-red-400">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="title" className="block text-xs font-medium text-slate-300">
              Project / Screenplay Title
            </label>
            <input
              id="title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="e.g. Borrowed Light"
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-xs font-medium text-slate-300">
              Description / Production Notes (Optional)
            </label>
            <textarea
              id="description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="Feature screenplay draft for pre-production clearance."
            />
          </div>

          <div className="flex items-center justify-end space-x-3 pt-2">
            <button
              type="button"
              onClick={() => navigate({ to: "/o/$orgSlug/projects", params: { orgSlug } })}
              className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold rounded-md shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              {loading ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default NewProjectRoute;

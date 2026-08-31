import React, { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/onboarding")({
  component: OnboardingRoute,
});

export function OnboardingRoute() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleNameChange = (val: string) => {
    setName(val);
    const suggested = val.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    setSlug(suggested);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await api.createOrganization({
        body: { name, slug },
      });

      if (!res.ok) {
        setError(res.error.message || "Could not create organization.");
        return;
      }

      navigate({
        to: "/o/$orgSlug",
        params: { orgSlug: slug },
      });
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="surface-onboarding min-h-screen flex items-center justify-center p-4 bg-slate-900 text-slate-100">
      <div className="card w-full max-w-md p-6 bg-slate-800 shadow rounded-lg border border-slate-700">
        <h1 className="text-2xl font-bold text-white mb-2">Create Workspace</h1>
        <p className="text-sm text-slate-400 mb-6">
          Set up your organization to start clearing screenplays.
        </p>

        {error && (
          <div
            role="alert"
            className="mb-4 p-3 rounded bg-red-950/50 border border-red-900 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label htmlFor="org-name" className="block text-sm font-medium text-slate-300">
              Organization Name
            </label>
            <input
              id="org-name"
              type="text"
              required
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-600 rounded-md shadow-sm bg-transparent text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="Indie Film Studio"
            />
          </div>

          <div>
            <label htmlFor="org-slug" className="block text-sm font-medium text-slate-300">
              Workspace URL Identifier
            </label>
            <div className="mt-1 flex rounded-md shadow-sm">
              <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-slate-600 bg-slate-700 text-slate-300 text-sm">
                clearcut.app/o/
              </span>
              <input
                id="org-slug"
                type="text"
                required
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="flex-1 min-w-0 block w-full px-3 py-2 border border-slate-600 rounded-r-md bg-transparent text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Organization"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default OnboardingRoute;

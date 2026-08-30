import React, { useState } from "react";

export function OnboardingRoute() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
      const res = await fetch("/api/v1/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, slug }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body?.detail || "Could not create organization.");
        return;
      }

      window.location.href = `/o/${slug}/projects`;
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="surface-onboarding min-h-screen flex items-center justify-center p-4">
      <div className="card w-full max-w-md p-6 bg-white dark:bg-slate-900 shadow rounded-lg border border-slate-200 dark:border-slate-800">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Create Workspace</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
          Set up your organization to start clearing screenplays.
        </p>

        {error && (
          <div
            role="alert"
            className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-sm text-red-700 dark:text-red-400"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label htmlFor="org-name" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
              Organization Name
            </label>
            <input
              id="org-name"
              type="text"
              required
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md shadow-sm bg-transparent text-slate-900 dark:text-white"
              placeholder="Indie Film Studio"
            />
          </div>

          <div>
            <label htmlFor="org-slug" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
              Workspace URL Identifier
            </label>
            <div className="mt-1 flex rounded-md shadow-sm">
              <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 text-sm">
                clearcut.app/o/
              </span>
              <input
                id="org-slug"
                type="text"
                required
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="flex-1 min-w-0 block w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-r-md bg-transparent text-slate-900 dark:text-white"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Organization"}
          </button>
        </form>
      </div>
    </div>
  );
}

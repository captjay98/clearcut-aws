import React, { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ThemeSwitcher } from "../../components/theme/ThemeSwitcher";

export const Route = createFileRoute("/auth/sign-in")({
  component: SignInRoute,
});

export function SignInRoute() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await api.createSession({
        body: { email, password },
      });

      if (!res.ok) {
        setError(res.error.message || "Invalid email or password. Please try again.");
        return;
      }

      const entryRes = await api.resolveOrganizationEntry();
      if (entryRes.ok && entryRes.value.data && entryRes.value.data.defaultOrgSlug) {
        navigate({
          to: "/o/$orgSlug/projects",
          params: { orgSlug: entryRes.value.data.defaultOrgSlug },
        });
      } else {
        navigate({ to: "/onboarding" });
      }
    } catch {
      setError("An unexpected network error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="surface-auth min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-slate-950 focus:font-bold focus:rounded-md"
      >
        Skip to main content
      </a>

      <header className="h-14 border-b border-slate-800 bg-slate-900/80 px-4 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="text-xl">🎬</span>
          <span className="font-bold text-amber-500 text-lg">ClearCut</span>
        </div>
        <ThemeSwitcher />
      </header>

      <main id="main-content" className="flex-1 flex items-center justify-center p-4">
        <div className="card w-full max-w-md p-6 bg-slate-900 shadow-xl rounded-lg border border-slate-800 text-slate-100">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-white">Sign In</h1>
            <p className="text-xs text-slate-400 mt-1">
              Screenplay Pre-Clearance & Evidence Workspace
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="mb-4 p-3 rounded bg-red-950/50 border border-red-900 text-xs text-red-400"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-medium text-slate-300"
              >
                Email Address
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="producer@studio.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-slate-300"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 border border-transparent rounded-md shadow text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In to Workspace"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

export default SignInRoute;

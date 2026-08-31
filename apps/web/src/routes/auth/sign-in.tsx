import React, { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

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
      if (entryRes.ok && entryRes.value.defaultOrgSlug) {
        navigate({
          to: "/o/$orgSlug",
          params: { orgSlug: entryRes.value.defaultOrgSlug },
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
    <div className="surface-auth min-h-screen flex items-center justify-center p-4">
      <div className="card w-full max-w-md p-6 bg-slate-900 shadow rounded-lg border border-slate-800 text-slate-100">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-white">ClearCut</h1>
          <p className="text-sm text-slate-400">
            Screenplay Pre-Clearance Workspace
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="mb-4 p-3 rounded bg-red-950/50 border border-red-900 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-slate-300"
            >
              Email Address
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-700 rounded-md shadow-sm bg-transparent text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="producer@studio.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-300"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-slate-700 rounded-md shadow-sm bg-transparent text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default SignInRoute;

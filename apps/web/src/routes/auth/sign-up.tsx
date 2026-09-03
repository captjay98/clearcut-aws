import React, { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ThemeSwitcher } from "../../components/theme/ThemeSwitcher";

export const Route = createFileRoute("/auth/sign-up")({
  component: SignUpRoute,
});

function registrationError(code: string, message: string): string {
  if (code === "conflict") {
    return "An account with this email address already exists. Sign in instead.";
  }
  if (code === "validation_failed") {
    return "Check your name, email address, and password. Passwords need at least 8 characters.";
  }
  if (code === "capability_unavailable") {
    return "Account registration is temporarily unavailable. Please try again later.";
  }
  return message || "Could not create your account. Please try again.";
}

export function SignUpRoute() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const result = await api.registerUser({
        body: { name, email, password },
      });
      if (!result.ok) {
        setError(registrationError(result.error.code, result.error.message));
        return;
      }

      const entry = await api.resolveOrganizationEntry();
      if (!entry.ok) {
        setError(
          "Your account was created, but workspace status could not be loaded. Sign in to continue.",
        );
        return;
      }

      if (entry.value.defaultOrgSlug) {
        navigate({
          to: "/o/$orgSlug/projects",
          params: { orgSlug: entry.value.defaultOrgSlug },
        });
        return;
      }
      navigate({ to: "/onboarding" });
    } catch {
      setError("A network error prevented account creation. Please try again.");
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
            <h1 className="text-2xl font-bold text-white">Create your account</h1>
            <p className="text-xs text-slate-400 mt-1">
              Start a sourced screenplay pre-clearance workspace.
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
              <label htmlFor="full-name" className="block text-xs font-medium text-slate-300">
                Full Name
              </label>
              <input
                id="full-name"
                type="text"
                autoComplete="name"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="Casey Morgan"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-xs font-medium text-slate-300">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="producer@studio.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-slate-300">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-describedby="password-help"
                className="mt-1 block w-full px-3 py-2 border border-slate-700 bg-slate-800 rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
              <p id="password-help" className="mt-1 text-xs text-slate-500">
                Use at least 8 characters.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 border border-transparent rounded-md shadow text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-slate-400">
            Already have an account?{" "}
            <Link to="/auth/sign-in" className="font-medium text-amber-500 hover:text-amber-400">
              Sign in
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

export default SignUpRoute;

import React, { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { PublicShell } from "../../components/shell/PublicShell";

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
      if (entryRes.ok && entryRes.value?.defaultOrgSlug) {
        navigate({
          to: "/o/$orgSlug/projects",
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
    <PublicShell
      eyebrow="Secure access"
      title="Sign in to ClearCut"
      lede="Reach your organization's clearance projects, their evidence, and the record of every decision."
    >
      <div>
        {error && (
          <div className="banner is-danger gap-b-6" role="alert">
            <span className="banner-icon" aria-hidden="true">
              ⚠
            </span>
            <div className="banner-body">
              <strong>Could not sign in</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        <article className="card card-accent">
          <form onSubmit={handleSubmit} className="stack">
            <div className="field">
              <label htmlFor="email">Email Address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="producer@studio.com"
              />
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="cluster" aria-busy={loading ? "true" : "false"}>
              <button className="button button-primary" type="submit" disabled={loading}>
                {loading ? "Signing in…" : "Sign In to Workspace"}
              </button>
              {loading && <span className="spinner" role="status" aria-label="Signing in" />}
            </div>
          </form>
        </article>

        <p className="small muted gap-t-4">
          New to ClearCut?{" "}
          <Link to="/auth/sign-up">Create an account</Link>
        </p>
      </div>
    </PublicShell>
  );
}

export default SignInRoute;

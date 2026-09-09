import React, { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { PublicShell } from "../../components/shell/PublicShell";

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
    <PublicShell
      eyebrow="Create an account"
      title="Create your account"
      lede="ClearCut is self-hosted. This account lives in the database you run, alongside the evidence and the audit trail it records."
    >
      <div className="auth-box">
        {error && (
          <div className="banner is-danger gap-b-6" role="alert">
            <span className="banner-icon" aria-hidden="true">
              ⚠
            </span>
            <div className="banner-body">
              <strong>Could not create your account</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        <article className="card card-accent">
          <form onSubmit={handleSubmit} className="stack">
            <div className="field">
              <label htmlFor="full-name">Full Name</label>
              <input
                id="full-name"
                type="text"
                autoComplete="name"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Casey Morgan"
              />
            </div>

            <div className="field">
              <label htmlFor="email">Email Address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="producer@studio.com"
              />
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-describedby="password-help"
              />
              <p id="password-help" className="field-hint">
                Use at least 8 characters.
              </p>
            </div>

            <div className="cluster" aria-busy={loading ? "true" : "false"}>
              <button className="button button-primary" type="submit" disabled={loading}>
                {loading ? "Creating account…" : "Create Account"}
              </button>
              {loading && <span className="spinner" role="status" aria-label="Creating account" />}
            </div>
          </form>
        </article>

        <p className="small muted gap-t-4">
          Already have an account? <Link to="/auth/sign-in">Sign in</Link>
        </p>
      </div>
    </PublicShell>
  );
}

export default SignUpRoute;

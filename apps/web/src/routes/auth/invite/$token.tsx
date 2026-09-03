import React, { useState } from "react";
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/auth/invite/$token")({
  component: AcceptInviteRoute,
});

export function AcceptInviteRoute() {
  const { token } = useParams({ from: "/auth/invite/$token" });
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAccept = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await api.acceptInvitation({ params: { token } });
      if (!res.ok) {
        setError(res.error.message || "Failed to accept invitation");
        return;
      }

      navigate({ to: "/o/$orgSlug", params: { orgSlug: "northlight" } });
    } catch {
      setError("An unexpected network error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-950 text-slate-100">
      <div className="card w-full max-w-md p-6 bg-slate-900 shadow rounded-lg border border-slate-800 text-center">
        <h1 className="text-xl font-bold text-white mb-2">Team Invitation</h1>
        <p className="text-xs text-slate-400 mb-6">
          You've been invited to join a ClearCut screenplay pre-clearance workspace.
        </p>

        {error && (
          <div role="alert" className="mb-4 p-3 bg-red-950/50 border border-red-900 rounded text-xs text-red-400">
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={handleAccept}
          disabled={loading}
          className="w-full py-2 px-4 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-xs font-bold text-white rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          {loading ? "Accepting..." : "Accept Invitation & Open Workspace"}
        </button>
      </div>
    </div>
  );
}

export default AcceptInviteRoute;

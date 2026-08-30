import React, { useState } from "react";

interface InviteRouteProps {
  token: string;
  invitation?: {
    orgName: string;
    role: string;
    email: string;
  };
}

export function InviteRoute({ token, invitation }: InviteRouteProps) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<"pending" | "accepted" | "declined" | "error">("pending");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleAccept = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/invitations/${token}/accept`, { method: "POST" });
      if (!res.ok) {
        setStatus("error");
        setErrorMessage("This invitation has expired or is no longer valid.");
        return;
      }
      setStatus("accepted");
      window.location.href = "/";
    } catch {
      setStatus("error");
      setErrorMessage("Network error processing invitation.");
    } finally {
      setLoading(false);
    }
  };

  const handleDecline = async () => {
    setLoading(true);
    try {
      await fetch(`/api/v1/invitations/${token}/decline`, { method: "POST" });
      setStatus("declined");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="surface-invite min-h-screen flex items-center justify-center p-4">
      <div className="card w-full max-w-md p-6 bg-white dark:bg-slate-900 shadow rounded-lg border border-slate-200 dark:border-slate-800 text-center">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Team Invitation</h1>

        {errorMessage && (
          <div
            role="alert"
            className="mb-4 p-3 rounded bg-red-50 dark:bg-red-950/50 border border-red-200 text-sm text-red-700 dark:text-red-400"
          >
            {errorMessage}
          </div>
        )}

        {status === "pending" && (
          <div>
            <p className="text-slate-600 dark:text-slate-400 mb-6">
              You have been invited to join <strong>{invitation?.orgName || "the organization"}</strong> as a <strong>{invitation?.role || "Reviewer"}</strong>.
            </p>
            <div className="flex gap-4 justify-center">
              <button
                type="button"
                onClick={handleDecline}
                disabled={loading}
                className="px-4 py-2 border border-slate-300 dark:border-slate-700 rounded text-slate-700 dark:text-slate-300 text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={handleAccept}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 font-medium"
              >
                {loading ? "Joining..." : "Accept Invitation"}
              </button>
            </div>
          </div>
        )}

        {status === "accepted" && (
          <p className="text-green-600 dark:text-green-400">Invitation accepted! Redirecting to workspace...</p>
        )}

        {status === "declined" && (
          <p className="text-slate-600 dark:text-slate-400">You have declined this invitation.</p>
        )}
      </div>
    </div>
  );
}

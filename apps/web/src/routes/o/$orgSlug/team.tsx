import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type Membership, type UserRole } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/team")({
  component: TeamRoute,
});

export function TeamRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/team" });
  const [members, setMembers] = useState<Membership[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("reviewer");
  const [loading, setLoading] = useState(true);
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadMembers = async () => {
    try {
      const result = await api.listOrganizationMembers({ params: { orgId: orgSlug } });
      if (result.ok) {
        setMembers(result.value);
      } else {
        setError(result.error.message);
      }
    } catch {
      setError("Failed to load members");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadMembers();
  }, [orgSlug]);

  const handleInvite = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setInviting(true);

    try {
      const result = await api.createInvitation({
        params: { orgId: orgSlug },
        body: { email, role },
      });

      if (!result.ok) {
        setError(result.error.message || "Failed to send invitation");
        return;
      }

      setSuccess(`Invitation sent to ${email}`);
      setEmail("");
      await loadMembers();
    } catch {
      setError("Network error while sending invitation");
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Team & Access</h1>
        <p className="text-sm text-slate-400">
          Manage workspace members, roles, and invitation access.
        </p>
      </div>

      <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
        <h2 className="text-sm font-bold text-slate-200 mb-3">Invite Team Member</h2>
        {error ? (
          <div role="alert" className="mb-3 p-2.5 bg-red-950/50 border border-red-900 text-xs text-red-400 rounded">
            {error}
          </div>
        ) : null}
        {success ? (
          <div role="status" className="mb-3 p-2.5 bg-emerald-950/50 border border-emerald-900 text-xs text-emerald-400 rounded">
            {success}
          </div>
        ) : null}

        <form onSubmit={handleInvite} className="flex flex-wrap gap-3 items-center">
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="colleague@studio.com"
            aria-label="Invitee email"
            className="flex-1 min-w-[240px] px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
          <select
            value={role}
            aria-label="Invitation role"
            onChange={(event) => setRole(event.target.value as UserRole)}
            className="px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            <option value="reviewer">Reviewer</option>
            <option value="editor">Editor</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            disabled={inviting}
            className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-xs font-bold text-white rounded focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {inviting ? "Inviting..." : "Send Invitation"}
          </button>
        </form>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-400">
          Current Members ({members.length})
        </div>
        {loading ? (
          <div className="p-6 text-center text-xs text-slate-500">Loading team...</div>
        ) : members.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">No members found.</div>
        ) : (
          <div className="divide-y divide-slate-800">
            {members.map((member) => (
              <div key={member.membershipId} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-slate-200">{member.email}</div>
                  <div className="text-xs text-slate-400 capitalize">{member.role}</div>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-[11px] px-2 py-0.5 bg-emerald-950 border border-emerald-900 text-emerald-400 rounded-full font-medium">
                    {member.active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default TeamRoute;

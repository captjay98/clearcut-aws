import React, { useState } from "react";

interface MemberItem {
  membershipId: string;
  email: string;
  role: "owner" | "admin" | "editor" | "reviewer";
  status: "active" | "deactivated";
}

interface TeamRouteProps {
  orgSlug: string;
  initialMembers?: MemberItem[];
  userRole?: string;
}

export function OrgTeamRoute({ orgSlug, initialMembers = [], userRole = "reviewer" }: TeamRouteProps) {
  const [members] = useState<MemberItem[]>(initialMembers);
  const canManage = userRole === "owner" || userRole === "admin";

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Team & Access</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">Organization: {orgSlug}</p>
        </div>

        {canManage && (
          <button
            type="button"
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
          >
            Invite Member
          </button>
        )}
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800">
          <thead className="bg-slate-50 dark:bg-slate-800/50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Member</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Role</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {members.map((m) => (
              <tr key={m.membershipId}>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900 dark:text-white">{m.email}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500 capitalize">{m.role}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500 capitalize">{m.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

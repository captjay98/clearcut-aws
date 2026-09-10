import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type Membership, type UserRole } from "@clearcut/contracts";
import { Badge, Banner, Card, EmptyState, Page, Section } from "../../../components/ds";
import { humanizeStatus } from "../../../features/clearance/itemPresentation";
import { canManageOrganizationSettings } from "../../../features/governance/capabilities";
import { TeamMemberControls } from "../../../features/team/TeamMemberControls";

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
  const [viewerRole, setViewerRole] = useState<UserRole | null>(null);

  // A local reading of the caller's role, used only to decide whether to offer
  // the governed per-member controls. The server authorizes every write again.
  const canManage = canManageOrganizationSettings(viewerRole);

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
    void (async () => {
      const session = await api.getSessionContext();
      if (session.ok) {
        setViewerRole(session.value.role ?? null);
      }
    })();
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

  // Governed per-member writes. Each throws on failure so the member's own
  // control surfaces the message, and refreshes the list on success — mirroring
  // the invite action's mutate-then-reload pattern.
  const handleChangeRole = async (member: Membership, nextRole: UserRole) => {
    setError(null);
    setSuccess(null);
    const result = await api.changeMembershipRole({
      params: { orgId: orgSlug, membershipId: member.membershipId },
      body: { role: nextRole },
    });
    if (!result.ok) {
      throw new Error(result.error.message || "Failed to change role");
    }
    setSuccess(`Role updated for ${member.email ?? member.userId}`);
    await loadMembers();
  };

  const handleChangeProjectGrant = async (member: Membership, projectIds: string[]) => {
    setError(null);
    setSuccess(null);
    const result = await api.changeProjectGrant({
      params: { orgId: orgSlug, membershipId: member.membershipId },
      body: { projectIds },
    });
    if (!result.ok) {
      throw new Error(result.error.message || "Failed to change project grants");
    }
    setSuccess(`Project grants updated for ${member.email ?? member.userId}`);
    await loadMembers();
  };

  const handleDeactivate = async (member: Membership) => {
    setError(null);
    setSuccess(null);
    const result = await api.deactivateMembership({
      params: { orgId: orgSlug, membershipId: member.membershipId },
    });
    if (!result.ok) {
      throw new Error(result.error.message || "Failed to deactivate member");
    }
    setSuccess(`Deactivated ${member.email ?? member.userId}`);
    await loadMembers();
  };

  const handleReactivate = async (member: Membership) => {
    setError(null);
    setSuccess(null);
    const result = await api.reactivateMembership({
      params: { orgId: orgSlug, membershipId: member.membershipId },
    });
    if (!result.ok) {
      throw new Error(result.error.message || "Failed to reactivate member");
    }
    setSuccess(`Reactivated ${member.email ?? member.userId}`);
    await loadMembers();
  };

  return (
    <Page
      trail={[{ label: "Team & roles" }]}
      eyebrow={orgSlug}
      title="Team & Access"
      lede="Manage workspace members, roles, and invitation access. Roles are fixed and enforced in the backend, not by hiding controls."
      notice={
        error ? (
          <Banner tone="is-danger" icon="⚠" title="Action failed" message={error} role="alert" />
        ) : success ? (
          <Banner tone="is-success" icon="✓" message={success} role="status" />
        ) : undefined
      }
    >
      <Section title="Invite team member">
        <Card>
          <form onSubmit={handleInvite}>
            <div className="form-grid">
              <label className="field" htmlFor="invitee-email">
                <span className="field-label">Invitee email</span>
                <input
                  id="invitee-email"
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="colleague@studio.com"
                  aria-label="Invitee email"
                />
              </label>
              <div className="field">
                <label className="field-label" htmlFor="invitation-role">
                  Invitation role
                </label>
                <select
                  id="invitation-role"
                  value={role}
                  onChange={(event) => setRole(event.target.value as UserRole)}
                >
                  <option value="reviewer">Reviewer</option>
                  <option value="editor">Editor</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <div className="cluster gap-t-4">
              <button className="button button-primary" type="submit" disabled={inviting}>
                {inviting ? "Inviting…" : "Send Invitation"}
              </button>
            </div>
          </form>
        </Card>
      </Section>

      <Section title={`Current Members (${members.length})`}>
        {loading ? (
          <p role="status" className="small muted">
            Loading team…
          </p>
        ) : members.length === 0 ? (
          <EmptyState
            icon="◉"
            title="No members found"
            description="Invite a colleague to give them a fixed role in this organization."
          />
        ) : (
          <div className="list">
            {members.map((member) => (
              <div className="list-row is-static" key={member.membershipId}>
                <div className="list-main">
                  <span className="list-title">{member.email}</span>
                  <span className="list-meta">
                    <span>{humanizeStatus(member.role)}</span>
                  </span>
                  <TeamMemberControls
                    member={member}
                    canManage={canManage}
                    onChangeRole={(nextRole) => handleChangeRole(member, nextRole)}
                    onChangeProjectGrant={(projectIds) =>
                      handleChangeProjectGrant(member, projectIds)
                    }
                    onDeactivate={() => handleDeactivate(member)}
                    onReactivate={() => handleReactivate(member)}
                  />
                </div>
                <div className="list-aside">
                  {/* Inactive is not a success state; it previously rendered in
                      the same green as Active. */}
                  <Badge tone={member.active ? "is-success" : ""}>
                    {member.active ? "Active" : "Inactive"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </Page>
  );
}

export default TeamRoute;

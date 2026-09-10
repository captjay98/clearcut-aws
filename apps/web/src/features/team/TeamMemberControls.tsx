import type { Membership, UserRole } from "@clearcut/contracts";
import React, { useState } from "react";
import { Banner } from "../../components/ds";

export interface TeamMemberControlsProps {
  member: Membership;
  /**
   * False for Editor, Reviewer and Viewer; the server authorizes again anyway.
   * When false the controls render read-only so a denial is never a surprise.
   */
  canManage: boolean;
  onChangeRole?: (role: UserRole) => Promise<void>;
  onChangeProjectGrant?: (projectIds: string[]) => Promise<void>;
  onDeactivate?: () => Promise<void>;
  onReactivate?: () => Promise<void>;
}

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "reviewer", label: "Reviewer" },
  { value: "editor", label: "Editor" },
  { value: "admin", label: "Admin" },
  { value: "owner", label: "Owner" },
];

/**
 * Per-member owner/admin controls: change role, change project grants, and
 * deactivate/reactivate. Each control keeps its own loading and error state and
 * calls an injected async callback, mirroring ItemGovernanceControls. The
 * boolean gate is a courtesy — every write is authorized again server-side.
 */
export function TeamMemberControls({
  member,
  canManage,
  onChangeRole,
  onChangeProjectGrant,
  onDeactivate,
  onReactivate,
}: TeamMemberControlsProps) {
  const [selectedRole, setSelectedRole] = useState<UserRole>(member.role);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [isChangingRole, setIsChangingRole] = useState(false);

  const [projectGrants, setProjectGrants] = useState(
    (member.projectGrants ?? []).join(", "),
  );
  const [grantError, setGrantError] = useState<string | null>(null);
  const [isChangingGrant, setIsChangingGrant] = useState(false);

  const [statusError, setStatusError] = useState<string | null>(null);
  const [isChangingStatus, setIsChangingStatus] = useState(false);

  if (!canManage) {
    return (
      <p className="small muted" tabIndex={0}>
        Role and access changes require an owner or admin.
      </p>
    );
  }

  const handleRoleChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!onChangeRole || selectedRole === member.role) return;

    setRoleError(null);
    setIsChangingRole(true);
    try {
      await onChangeRole(selectedRole);
    } catch (submissionError) {
      setRoleError(
        submissionError instanceof Error
          ? submissionError.message
          : "The role change was not recorded.",
      );
    } finally {
      setIsChangingRole(false);
    }
  };

  const handleGrantChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!onChangeProjectGrant) return;

    const projectIds = projectGrants
      .split(",")
      .map((value) => value.trim())
      .filter((value) => value.length > 0);

    setGrantError(null);
    setIsChangingGrant(true);
    try {
      await onChangeProjectGrant(projectIds);
    } catch (submissionError) {
      setGrantError(
        submissionError instanceof Error
          ? submissionError.message
          : "The project grant change was not recorded.",
      );
    } finally {
      setIsChangingGrant(false);
    }
  };

  const handleStatusChange = async () => {
    const action = member.active ? onDeactivate : onReactivate;
    if (!action) return;

    setStatusError(null);
    setIsChangingStatus(true);
    try {
      await action();
    } catch (submissionError) {
      setStatusError(
        submissionError instanceof Error
          ? submissionError.message
          : member.active
            ? "The deactivation was not recorded."
            : "The reactivation was not recorded.",
      );
    } finally {
      setIsChangingStatus(false);
    }
  };

  return (
    <div className="stack" aria-label={`Controls for ${member.email ?? member.userId}`}>
      <form onSubmit={handleRoleChange} className="cluster">
        <div className="field">
          <label className="field-label" htmlFor={`role-${member.membershipId}`}>
            Role
          </label>
          <select
            id={`role-${member.membershipId}`}
            value={selectedRole}
            disabled={isChangingRole}
            onChange={(event) => setSelectedRole(event.target.value as UserRole)}
          >
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <button
          className="button button-secondary button-sm"
          type="submit"
          disabled={isChangingRole || selectedRole === member.role}
        >
          {isChangingRole ? "Saving…" : "Change Role"}
        </button>
      </form>
      {roleError && (
        <Banner tone="is-danger" icon="⚠" message={roleError} role="alert" />
      )}

      <form onSubmit={handleGrantChange} className="cluster">
        <label className="field" htmlFor={`grants-${member.membershipId}`}>
          <span className="field-label">Project grants (comma-separated IDs)</span>
          <input
            id={`grants-${member.membershipId}`}
            value={projectGrants}
            disabled={isChangingGrant}
            placeholder="No project grants"
            onChange={(event) => setProjectGrants(event.target.value)}
          />
        </label>
        <button
          className="button button-secondary button-sm"
          type="submit"
          disabled={isChangingGrant}
        >
          {isChangingGrant ? "Saving…" : "Change Grants"}
        </button>
      </form>
      {grantError && (
        <Banner tone="is-danger" icon="⚠" message={grantError} role="alert" />
      )}

      <div className="cluster">
        <button
          className={member.active ? "button button-danger button-sm" : "button button-secondary button-sm"}
          type="button"
          disabled={isChangingStatus}
          onClick={handleStatusChange}
        >
          {isChangingStatus
            ? "Saving…"
            : member.active
              ? "Deactivate"
              : "Reactivate"}
        </button>
      </div>
      {statusError && (
        <Banner tone="is-danger" icon="⚠" message={statusError} role="alert" />
      )}
    </div>
  );
}

export default TeamMemberControls;

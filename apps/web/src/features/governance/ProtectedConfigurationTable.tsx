import React from "react";
import type { ProtectedConfiguration } from "@clearcut/contracts";
import { Badge, DataTable, EmptyState } from "../../components/ds";
import type { Tone } from "../../components/ds";

const LIFECYCLE_LABELS: Readonly<
  Record<ProtectedConfiguration["lifecycle"], { label: string; tone: Tone }>
> = {
  draft: { label: "Draft", tone: "is-warning" },
  validated: { label: "Validated", tone: "is-accent" },
  active: { label: "Active", tone: "is-success" },
  superseded: { label: "Superseded", tone: "" },
};

function stamp(value: string | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

export interface ProtectedConfigurationTableProps {
  configurations: readonly ProtectedConfiguration[];
  /** False for every role but Owner; the server authorizes again regardless. */
  canGovern: boolean;
  pendingConfigurationId: string | null;
  onValidate: (configurationId: string) => void;
  onActivate: (configurationId: string) => void;
}

/**
 * The organization's protected configuration bindings.
 *
 * The offered action follows the persisted lifecycle: a draft may be validated, a
 * validated version may be activated, and an active or superseded version offers
 * nothing, because an active version is immutable — changing one supersedes it
 * and writes an audit event in the same transaction. Validation issues are shown
 * verbatim rather than summarised as "invalid".
 */
export function ProtectedConfigurationTable({
  configurations,
  canGovern,
  pendingConfigurationId,
  onValidate,
  onActivate,
}: ProtectedConfigurationTableProps) {
  if (configurations.length === 0) {
    return (
      <EmptyState
        icon="⚖"
        title="No protected configuration recorded yet"
        description="Until a version is drafted, validated and activated, this organization runs on the platform defaults. No version is inferred for it."
      />
    );
  }

  const rows = configurations.map((configuration) => {
    const lifecycle = LIFECYCLE_LABELS[configuration.lifecycle] ?? {
      label: configuration.lifecycle,
      tone: "" as Tone,
    };
    const busy = pendingConfigurationId === configuration.configurationId;
    const issues = configuration.validationIssues ?? [];

    return [
      <>
        <strong className="small">{configuration.label ?? "Unlabelled version"}</strong>
        {configuration.rationale && (
          <>
            <br />
            <span className="small muted">{configuration.rationale}</span>
          </>
        )}
      </>,
      <span className="mono small">
        policy {configuration.policyVersion}
        <br />
        prompt {configuration.promptVersion}
      </span>,
      <Badge tone={lifecycle.tone}>{lifecycle.label}</Badge>,
      <span className="mono small">
        {stamp(configuration.activatedAt)}
        {configuration.activatedBy && (
          <>
            <br />
            <span className="muted">{configuration.activatedBy}</span>
          </>
        )}
      </span>,
      issues.length > 0 ? (
        <ul className="stack-sm">
          {issues.map((issue) => (
            <li className="small" key={issue}>
              {issue}
            </li>
          ))}
        </ul>
      ) : configuration.validatedAt ? (
        <span className="small">No issues found {stamp(configuration.validatedAt)}</span>
      ) : (
        <span className="small muted">Not validated yet</span>
      ),
      <div className="cluster cluster-end">
        {canGovern && configuration.lifecycle === "draft" && (
          <button
            className="button button-secondary button-sm"
            type="button"
            disabled={busy}
            onClick={() => onValidate(configuration.configurationId)}
          >
            {busy ? "Working…" : "Validate"}
          </button>
        )}
        {canGovern && configuration.lifecycle === "validated" && (
          <button
            className="button button-primary button-sm"
            type="button"
            disabled={busy}
            onClick={() => onActivate(configuration.configurationId)}
          >
            {busy ? "Working…" : "Activate"}
          </button>
        )}
        {configuration.lifecycle === "active" && (
          <span className="small muted">Immutable while active</span>
        )}
        {configuration.lifecycle === "superseded" && (
          <span className="small muted">
            Superseded {stamp(configuration.supersededAt)}
          </span>
        )}
      </div>,
    ];
  });

  return (
    <div data-testid="protected-configuration-table">
      <DataTable
        caption="Organization-owned protected configuration"
        columns={[
          { label: "Policy" },
          { label: "Bound versions" },
          { label: "Status" },
          { label: "Activated" },
          { label: "Validation" },
          { label: "Actions", align: "right" },
        ]}
        rows={rows}
      />
    </div>
  );
}

export default ProtectedConfigurationTable;

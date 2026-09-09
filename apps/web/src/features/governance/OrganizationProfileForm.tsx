import React, { useEffect, useState } from "react";
import type { OrganizationSettings } from "@clearcut/contracts";
import { Banner, Card } from "../../components/ds";
import {
  CADENCE_ORDER,
  cadenceLabel,
  isMonitoringCadence,
  type MonitoringCadence,
} from "./cadence";

export interface OrganizationProfileFormProps {
  settings: OrganizationSettings;
  /** False for Editor, Reviewer and Viewer; the server authorizes again anyway. */
  canManage: boolean;
  saving: boolean;
  /** Set when the save was rejected because the record moved underneath us. */
  staleConflict: boolean;
  error?: string | null;
  saved: boolean;
  onSave: (input: {
    name: string;
    jurisdiction?: string;
    defaultMonitoringCadence: MonitoringCadence;
    expectedVersion: number;
  }) => void;
}

/**
 * The organization profile, editable by Owner and Admin.
 *
 * Three things this form deliberately does not do:
 *  - it does not offer an evidence retention duration, because there is none:
 *    evidence is kept until an Owner deletes the project or the organization;
 *  - it does not let the slug be edited, because identifiers already in use
 *    elsewhere are not renamed from a settings pane;
 *  - it never prints a raw cadence token. Every reading goes through the label
 *    map, so the stored value and the displayed one cannot drift.
 *
 * The select uses a sibling `<label htmlFor>` inside `div.field` rather than a
 * wrapping label: a wrapping label folds the selected option's text into the
 * control's accessible name, so the field would announce itself differently
 * depending on what happened to be selected.
 */
export function OrganizationProfileForm({
  settings,
  canManage,
  saving,
  staleConflict,
  error,
  saved,
  onSave,
}: OrganizationProfileFormProps) {
  const [name, setName] = useState(settings.name);
  const [jurisdiction, setJurisdiction] = useState(settings.jurisdiction ?? "");
  const [cadence, setCadence] = useState<MonitoringCadence>(
    settings.defaultMonitoringCadence,
  );

  // Re-base the editor whenever the authoritative record changes — including the
  // refetch that follows a stale-version rejection, so the next save is compared
  // against what is actually stored rather than the version we started from.
  useEffect(() => {
    setName(settings.name);
    setJurisdiction(settings.jurisdiction ?? "");
    setCadence(settings.defaultMonitoringCadence);
  }, [settings.version, settings.name, settings.jurisdiction, settings.defaultMonitoringCadence]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onSave({
      name: name.trim(),
      ...(jurisdiction.trim() ? { jurisdiction: jurisdiction.trim() } : {}),
      defaultMonitoringCadence: cadence,
      expectedVersion: settings.version,
    });
  };

  return (
    <Card testId="organization-profile-form">
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <div className="field field-full">
            <label className="field-label" htmlFor="org-name">
              Organization name
            </label>
            <input
              id="org-name"
              value={name}
              required
              readOnly={!canManage}
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="org-slug">
              Workspace address
            </label>
            <input id="org-slug" value={settings.slug} readOnly />
            <p className="field-hint">
              Not editable here: it is already in use in links and records.
            </p>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="org-jurisdiction">
              Primary jurisdiction
            </label>
            <input
              id="org-jurisdiction"
              value={jurisdiction}
              readOnly={!canManage}
              placeholder="Not declared"
              onChange={(event) => setJurisdiction(event.target.value)}
            />
          </div>

          <div className="field">
            <span className="field-label">Evidence retention</span>
            <p className="small gap-t-1">
              Kept until an Owner deletes the project or organization. There is no
              age-based expiry, so there is nothing to set here.
            </p>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="org-cadence">
              Default monitoring cadence
            </label>
            <select
              id="org-cadence"
              value={cadence}
              disabled={!canManage}
              onChange={(event) => {
                const next = event.target.value;
                if (isMonitoringCadence(next)) setCadence(next);
              }}
            >
              {CADENCE_ORDER.map((value) => (
                <option key={value} value={value}>
                  {cadenceLabel(value)}
                </option>
              ))}
            </select>
            <p className="field-hint">
              Currently {cadenceLabel(settings.defaultMonitoringCadence)}.
            </p>
          </div>
        </div>

        {staleConflict && (
          <div className="gap-t-4">
            <Banner
              tone="is-warning"
              icon="⚠"
              title="Someone else saved first"
              message="These settings changed while you were editing, so your save was rejected rather than applied over theirs. The current values have been reloaded — review them and save again if you still want your change."
              role="alert"
              titleIsHeading
            />
          </div>
        )}

        {error && !staleConflict && (
          <div className="gap-t-4">
            <Banner
              tone="is-danger"
              icon="⚠"
              title="Settings were not saved"
              message={error}
              role="alert"
              titleIsHeading
            />
          </div>
        )}

        {saved && !staleConflict && !error && (
          <div className="gap-t-4">
            <Banner
              tone="is-success"
              icon="✓"
              message={`Saved. Monitoring cadence is ${cadenceLabel(settings.defaultMonitoringCadence)}.`}
              role="status"
            />
          </div>
        )}

        {canManage ? (
          <div className="cluster gap-t-4">
            <button className="button button-primary" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        ) : (
          <div className="gap-t-4">
            <Banner
              icon="⚖"
              message="Organization settings are changed by an Owner or Admin. You are seeing the stored values, which is the whole record — nothing is hidden from this view."
            />
          </div>
        )}
      </form>
    </Card>
  );
}

export default OrganizationProfileForm;

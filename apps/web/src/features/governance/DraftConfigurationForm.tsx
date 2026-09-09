import React, { useState } from "react";
import { Banner, Card } from "../../components/ds";
import type { DraftProtectedConfigurationInput } from "../../mutations/governanceCommands";

export interface DraftConfigurationFormProps {
  saving: boolean;
  error?: string | null;
  drafted: boolean;
  onDraft: (input: DraftProtectedConfigurationInput) => void;
}

/**
 * Drafting a new protected configuration version.
 *
 * A rationale is required by the contract and required here too: an activated
 * version is immutable and supersedes its predecessor, so the reason it was
 * raised is part of the record rather than an optional note. Drafting alone
 * changes nothing in force — it must be validated and then activated.
 */
export function DraftConfigurationForm({
  saving,
  error,
  drafted,
  onDraft,
}: DraftConfigurationFormProps) {
  const [label, setLabel] = useState("");
  const [policyVersion, setPolicyVersion] = useState("");
  const [promptVersion, setPromptVersion] = useState("");
  const [rationale, setRationale] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onDraft({
      ...(label.trim() ? { label: label.trim() } : {}),
      policyVersion: policyVersion.trim(),
      promptVersion: promptVersion.trim(),
      rationale: rationale.trim(),
    });
    setLabel("");
    setPolicyVersion("");
    setPromptVersion("");
    setRationale("");
  };

  return (
    <Card
      eyebrow="Owner only"
      title="Draft a new version"
      testId="draft-protected-configuration"
    >
      <form onSubmit={handleSubmit}>
        <p className="small muted">
          A draft changes nothing in force. It has to be validated, then activated
          by an Owner, and activation supersedes the version before it and writes
          an audit event in the same transaction.
        </p>
        <div className="form-grid gap-t-4">
          <div className="field field-full">
            <label className="field-label" htmlFor="draft-label">
              Label
            </label>
            <input
              id="draft-label"
              value={label}
              placeholder="Optional, e.g. Q4 clearance policy"
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="draft-policy-version">
              Policy version
            </label>
            <input
              id="draft-policy-version"
              value={policyVersion}
              required
              onChange={(event) => setPolicyVersion(event.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="draft-prompt-version">
              Prompt version
            </label>
            <input
              id="draft-prompt-version"
              value={promptVersion}
              required
              onChange={(event) => setPromptVersion(event.target.value)}
            />
          </div>
          <div className="field field-full">
            <label className="field-label" htmlFor="draft-rationale">
              Why this version is being raised
            </label>
            <textarea
              id="draft-rationale"
              value={rationale}
              required
              rows={3}
              onChange={(event) => setRationale(event.target.value)}
            />
          </div>
        </div>

        {error && (
          <div className="gap-t-4">
            <Banner
              tone="is-danger"
              icon="⚠"
              title="The draft was not created"
              message={error}
              role="alert"
              titleIsHeading
            />
          </div>
        )}
        {drafted && !error && (
          <div className="gap-t-4">
            <Banner
              tone="is-success"
              icon="✓"
              message="Draft recorded. It is not in force until it is validated and activated."
              role="status"
            />
          </div>
        )}

        <div className="cluster gap-t-4">
          <button className="button button-secondary" type="submit" disabled={saving}>
            {saving ? "Recording…" : "Record draft"}
          </button>
        </div>
      </form>
    </Card>
  );
}

export default DraftConfigurationForm;

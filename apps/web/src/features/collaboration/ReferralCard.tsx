import type { ItemCapability, ItemReferral } from "@clearcut/contracts";
import React, { useState } from "react";
import { Badge, Banner, Card } from "../../components/ds";
import { humanizeStatus } from "../clearance/itemPresentation";

export interface ReferralCardProps {
  itemId: string;
  referrals: ItemReferral[];
  referralCapability?: ItemCapability;
  onRefer?: (
    targetRole: string,
    question: string,
    rationale: string,
  ) => Promise<void>;
  onAcknowledge?: (
    referralId: string,
    response: string,
    rationale: string,
  ) => Promise<void>;
}

interface ReferralAcknowledgementFormProps {
  referralId: string;
  onAcknowledge: NonNullable<ReferralCardProps["onAcknowledge"]>;
}

function ReferralAcknowledgementForm({
  referralId,
  onAcknowledge,
}: ReferralAcknowledgementFormProps) {
  const [response, setResponse] = useState("");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAcknowledge = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!response.trim() || !rationale.trim()) return;

    setError(null);
    setIsSubmitting(true);
    try {
      await onAcknowledge(referralId, response.trim(), rationale.trim());
      setResponse("");
      setRationale("");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "The referral acknowledgement was not recorded.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleAcknowledge} className="stack-sm gap-t-4">
      <div className="divider" />
      <div className="field">
        <label className="field-label" htmlFor={`referral-response-${referralId}`}>
          Referral response
        </label>
        <textarea
          id={`referral-response-${referralId}`}
          rows={2}
          required
          value={response}
          onChange={(event) => setResponse(event.target.value)}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor={`acknowledgement-rationale-${referralId}`}>
          Acknowledgement rationale
        </label>
        <textarea
          id={`acknowledgement-rationale-${referralId}`}
          rows={2}
          required
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
        />
      </div>
      {error && <Banner tone="is-danger" icon="⚠" message={error} role="alert" />}
      <div className="cluster">
        <button className="button button-secondary button-sm" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Acknowledging…" : "Acknowledge Referral"}
        </button>
      </div>
    </form>
  );
}

export function ReferralCard({
  itemId,
  referrals,
  referralCapability,
  onRefer,
  onAcknowledge,
}: ReferralCardProps) {
  const [targetRole, setTargetRole] = useState("counsel");
  const [question, setQuestion] = useState("");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const referralAllowed = referralCapability?.allowed ?? Boolean(onRefer);

  const handleRefer = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!question.trim() || !rationale.trim() || !onRefer || !referralAllowed) return;

    setError(null);
    setIsSubmitting(true);
    try {
      await onRefer(targetRole, question.trim(), rationale.trim());
      setQuestion("");
      setRationale("");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "The referral could not be submitted.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="section" data-testid="referral-section" data-item-id={itemId}>
      <div className="section-head">
        <div>
          <h2>Specialist referral</h2>
          <p>
            A referral hands the question to a named role and is acknowledged by a different
            accountable person.
          </p>
        </div>
      </div>

      {referrals.length > 0 ? (
        <ol
          className="stack gap-b-4"
          aria-label="Referral history"
          style={{ listStyle: "none", padding: 0 }}
        >
          {referrals.map((referral) => (
            <li className="source-card" key={referral.referralId}>
              <div className="cluster-between">
                <strong className="small">{humanizeStatus(referral.targetRole)}</strong>
                {/* The server's own status token, shown verbatim rather than
                    prettified, so what is displayed is what was recorded. */}
                <Badge tone={referral.status === "acknowledged" ? "is-success" : "is-warning"}>
                  {referral.status}
                </Badge>
              </div>
              <p className="small gap-t-2">{referral.question}</p>
              {referral.notes && <p className="small muted gap-t-1">{referral.notes}</p>}
              {referral.status !== "acknowledged" && onAcknowledge && (
                <ReferralAcknowledgementForm
                  referralId={referral.referralId}
                  onAcknowledge={onAcknowledge}
                />
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="small muted gap-b-4">No referrals have been recorded.</p>
      )}

      <Card>
        <p className="small muted" tabIndex={0}>
          {referralCapability?.explanation ??
            "Referral capability is unavailable for this item and current role."}
        </p>

        <form onSubmit={handleRefer} className="gap-t-4">
          <div className="form-grid">
            <div className="field">
              <label className="field-label" htmlFor="target-role">
                Refer To Specialist Role
              </label>
              <select
                id="target-role"
                value={targetRole}
                disabled={!referralAllowed}
                onChange={(event) => setTargetRole(event.target.value)}
              >
                <option value="reviewer">Project Reviewer (Internal)</option>
                <option value="counsel">Legal Counsel (External/Production)</option>
                <option value="trademark_specialist">Trademark &amp; Title Specialist</option>
                <option value="music_supervisor">Music Clearance Supervisor</option>
                <option value="lead_producer">Lead Production Executive</option>
              </select>
            </div>

            <div className="field field-full">
              <label className="field-label" htmlFor="referral-question">
                Referral question
              </label>
              <textarea
                id="referral-question"
                required
                rows={2}
                value={question}
                disabled={!referralAllowed}
                onChange={(event) => setQuestion(event.target.value)}
              />
            </div>

            <div className="field field-full">
              <label className="field-label" htmlFor="referral-rationale">
                Accountable rationale
              </label>
              <textarea
                id="referral-rationale"
                required
                rows={2}
                value={rationale}
                disabled={!referralAllowed}
                onChange={(event) => setRationale(event.target.value)}
              />
            </div>
          </div>

          {error && (
            <Banner tone="is-danger" icon="⚠" message={error} role="alert" className="gap-t-3" />
          )}

          <div className="cluster gap-t-4" style={{ justifyContent: "flex-end" }}>
            <button
              className="button button-primary"
              type="submit"
              disabled={isSubmitting || !onRefer || !referralAllowed}
            >
              {isSubmitting ? "Submitting…" : "Send Formal Referral"}
            </button>
          </div>
        </form>
      </Card>
    </section>
  );
}

export default ReferralCard;

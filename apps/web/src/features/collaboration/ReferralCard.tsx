import type { ItemCapability, ItemReferral } from "@clearcut/contracts";
import React, { useState } from "react";

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
    <form onSubmit={handleAcknowledge} className="mt-3 space-y-2 border-t border-slate-800 pt-3">
      <label htmlFor={`referral-response-${referralId}`} className="block text-slate-400">
        Referral response
      </label>
      <textarea
        id={`referral-response-${referralId}`}
        rows={2}
        required
        value={response}
        onChange={(event) => setResponse(event.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-white"
      />
      <label htmlFor={`acknowledgement-rationale-${referralId}`} className="block text-slate-400">
        Acknowledgement rationale
      </label>
      <textarea
        id={`acknowledgement-rationale-${referralId}`}
        rows={2}
        required
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-white"
      />
      {error ? <p role="alert" className="text-red-400">{error}</p> : null}
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-slate-700 px-3 py-1.5 font-semibold text-white disabled:opacity-50"
      >
        {isSubmitting ? "Acknowledging…" : "Acknowledge Referral"}
      </button>
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
    <div
      data-testid="referral-section"
      data-item-id={itemId}
      className="space-y-4 font-sans"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Specialist Referral Workflow</span>
        <span className="text-[10px] text-slate-500 font-normal">
          Multi-Discipline Sign-Off
        </span>
      </div>

      {referrals.length > 0 ? (
        <ol aria-label="Referral history" className="space-y-2">
          {referrals.map((referral) => (
            <li
              key={referral.referralId}
              className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs text-slate-300"
            >
              <div className="flex justify-between gap-3">
                <span className="font-semibold text-white">{referral.targetRole}</span>
                <span className="uppercase text-slate-500">{referral.status}</span>
              </div>
              <p className="mt-2">{referral.question}</p>
              {referral.notes ? <p className="mt-1 text-slate-400">{referral.notes}</p> : null}
              {referral.status !== "acknowledged" && onAcknowledge ? (
                <ReferralAcknowledgementForm
                  referralId={referral.referralId}
                  onAcknowledge={onAcknowledge}
                />
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-xs text-slate-500">No referrals have been recorded.</p>
      )}

      <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-3 shadow-sm">
        <p tabIndex={0} className="text-xs text-slate-400">
          {referralCapability?.explanation ??
            "Referral capability is unavailable for this item and current role."}
        </p>
        <form onSubmit={handleRefer} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label htmlFor="target-role" className="block text-slate-400 font-medium mb-1">
                Refer To Specialist Role
              </label>
              <select
                id="target-role"
                value={targetRole}
                disabled={!referralAllowed}
                onChange={(event) => setTargetRole(event.target.value)}
                className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-white text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="reviewer">Project Reviewer (Internal)</option>
                <option value="counsel">Legal Counsel (External/Production)</option>
                <option value="trademark_specialist">Trademark & Title Specialist</option>
                <option value="music_supervisor">Music Clearance Supervisor</option>
                <option value="lead_producer">Lead Production Executive</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="referral-question" className="block text-slate-400 font-medium mb-1 text-xs">
              Referral question
            </label>
            <textarea
              id="referral-question"
              required
              rows={2}
              value={question}
              disabled={!referralAllowed}
              onChange={(event) => setQuestion(event.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-white text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div>
            <label htmlFor="referral-rationale" className="block text-slate-400 font-medium mb-1 text-xs">
              Accountable rationale
            </label>
            <textarea
              id="referral-rationale"
              required
              rows={2}
              value={rationale}
              disabled={!referralAllowed}
              onChange={(event) => setRationale(event.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded text-white text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          {error ? <p role="alert" className="text-xs text-red-400">{error}</p> : null}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting || !onRefer || !referralAllowed}
              className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50 text-white font-bold text-xs rounded shadow"
            >
              {isSubmitting ? "Submitting…" : "Send Formal Referral"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ReferralCard;

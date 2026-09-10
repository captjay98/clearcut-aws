import React, { useEffect, useState } from "react";
import type { NotificationDeliveryPreference } from "@clearcut/contracts";
import { Banner, Card } from "../../components/ds";

export type DeliveryChannel = NotificationDeliveryPreference["channel"];

/** Ordered channels with human labels; the raw token is never printed. */
const CHANNEL_ORDER: readonly DeliveryChannel[] = ["in_app", "email", "push"];

const CHANNEL_LABELS: Record<DeliveryChannel, string> = {
  in_app: "In-app only",
  email: "Email",
  push: "Push notification",
};

function isDeliveryChannel(value: string): value is DeliveryChannel {
  return (CHANNEL_ORDER as readonly string[]).includes(value);
}

function channelLabel(channel: DeliveryChannel): string {
  return CHANNEL_LABELS[channel];
}

export interface NotificationDeliveryPreferenceFormProps {
  /** The stored channel. Defaulted upstream when no read endpoint exists. */
  channel: DeliveryChannel;
  saving: boolean;
  saved: boolean;
  error?: string | null;
  /** Called with the newly selected channel; the parent runs the mutation. */
  onChange: (channel: DeliveryChannel) => void;
}

/**
 * The caller's own notification delivery channel.
 *
 * This is a personal preference rather than a governed action, so there is no
 * capability gate: any active member may set their own channel. The contract
 * exposes a setter but no reader, so the selected value is defaulted upstream
 * and re-based here whenever the authoritative (or defaulted) value changes.
 *
 * The label is a sibling of the `<select>` rather than a wrapper: a wrapping
 * label folds the selected option's text into the control's accessible name,
 * so the field would announce itself differently depending on the selection.
 */
export function NotificationDeliveryPreferenceForm({
  channel,
  saving,
  saved,
  error,
  onChange,
}: NotificationDeliveryPreferenceFormProps) {
  const [selected, setSelected] = useState<DeliveryChannel>(channel);

  // Re-base on the authoritative value, including the cache write that follows
  // a successful save, so the control shows what is actually stored.
  useEffect(() => {
    setSelected(channel);
  }, [channel]);

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value;
    if (!isDeliveryChannel(next) || next === selected) return;
    setSelected(next);
    onChange(next);
  };

  return (
    <Card testId="notification-delivery-preference-form">
      <div className="field">
        <label className="field-label" htmlFor="notification-delivery-channel">
          Notification delivery
        </label>
        <select
          id="notification-delivery-channel"
          value={selected}
          disabled={saving}
          onChange={handleChange}
        >
          {CHANNEL_ORDER.map((value) => (
            <option key={value} value={value}>
              {channelLabel(value)}
            </option>
          ))}
        </select>
        <p className="field-hint">
          Where you receive alerts for reviews, referrals and monitoring. This is
          your own preference and changes nothing for anyone else. Saved on
          change.
        </p>
      </div>

      {saving && (
        <p role="status" className="small muted gap-t-3">
          Saving…
        </p>
      )}

      {error && (
        <div className="gap-t-3">
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Delivery preference was not saved"
            message={error}
            role="alert"
            titleIsHeading
          />
        </div>
      )}

      {saved && !error && !saving && (
        <div className="gap-t-3">
          <Banner
            tone="is-success"
            icon="✓"
            message={`Saved. Delivery is ${channelLabel(selected)}.`}
            role="status"
          />
        </div>
      )}
    </Card>
  );
}

export default NotificationDeliveryPreferenceForm;

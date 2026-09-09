import React from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { Badge, Banner, Card, Page, Section } from "../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/settings")({
  component: SettingsRoute,
});

/**
 * Organization policy is a protected configuration: permissions, sign-off
 * policy, source-authority tiers and retention are human-only and Owner
 * governed. There is no write endpoint for them in this build, so this surface
 * reports the active policy rather than offering controls.
 *
 * It previously rendered checked checkboxes with no handler and no request
 * behind them, which invited a reader to believe they had changed a governance
 * rule when nothing was recorded.
 */
const GOVERNANCE_POLICY: readonly {
  name: string;
  description: string;
  value: string;
  active: boolean;
}[] = [
  {
    name: "Dual legal sign-off",
    description: "Require two qualified reviewers before a release export.",
    value: "Required",
    active: true,
  },
  {
    name: "Strict source authority",
    description:
      "Reject non-canonical sources during automated evidence extraction; a rejected source becomes a review item, never a silent pass.",
    value: "Enforced",
    active: true,
  },
  {
    name: "Retention horizon",
    description: "Days before inactive audit payloads are archived.",
    value: "365 days",
    active: true,
  },
];

export function SettingsRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/settings" });

  return (
    <Page
      trail={[{ label: "Settings" }]}
      eyebrow={orgSlug}
      title="Workspace Settings"
      lede="Organization policies, retention periods, and verification thresholds."
      notice={
        <Banner
          icon="⚖"
          title="Protected configuration"
          message="These are human-only, Owner-governed rules. Changing them is a governed action that writes an audit event, and it is not exposed in this build — so they are shown here as the active policy rather than as controls."
        />
      }
    >
      <Section
        title="Clearance governance"
        description="The policy every governed decision in this organization is evaluated against."
      >
        <Card>
          {GOVERNANCE_POLICY.map((policy) => (
            <div className="toggle-row" key={policy.name}>
              <div>
                <strong className="small">{policy.name}</strong>
                <p className="field-hint">{policy.description}</p>
              </div>
              <Badge tone={policy.active ? "is-success" : ""}>{policy.value}</Badge>
            </div>
          ))}
        </Card>
      </Section>
    </Page>
  );
}

export default SettingsRoute;

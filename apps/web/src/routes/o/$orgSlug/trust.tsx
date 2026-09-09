import React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Banner, Page } from "../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/trust")({
  component: TrustRoute,
});

export function TrustRoute() {
  return (
    <Page
      trail={[{ label: "AI trust" }]}
      eyebrow="Evaluation"
      title="Trust Center & Evaluation Rubric"
      lede="Persisted quality evaluations, protected policy versions, and human-gated learning lifecycles will appear here."
    >
      {/* Deliberately reports absence rather than rendering a rubric or a score.
          A judged dimension with no persisted evaluation behind it would be an
          invented number. */}
      <Banner
        tone="is-warning"
        icon="○"
        title="No persisted evaluation yet"
        message="The Trust evaluation capability is not available until a project run has persisted its deterministic and judge evaluations. No score or policy status is inferred in the meantime."
        role="status"
      />
    </Page>
  );
}

export default TrustRoute;

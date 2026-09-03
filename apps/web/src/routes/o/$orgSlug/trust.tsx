import React from "react";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/o/$orgSlug/trust")({
  component: TrustRoute,
});

export function TrustRoute() {
  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div>
        <h1 className="text-2xl font-bold text-white">Trust Center & Evaluation Rubric</h1>
        <p className="text-sm text-slate-400">
          Persisted quality evaluations, protected policy versions, and human-gated learning
          lifecycles will appear here.
        </p>
      </div>

      <div
        role="status"
        className="rounded-lg border border-amber-900 bg-amber-950/40 p-5 text-sm text-amber-200"
      >
        The Trust evaluation capability is not available until a project run has persisted its
        deterministic and judge evaluations. No score or policy status is inferred in the meantime.
      </div>
    </div>
  );
}

export default TrustRoute;

import React from "react";
import type { DeterministicGateResult } from "@clearcut/contracts";
import { Badge, Card } from "../../components/ds";
import { gateLabel, gateOutcome } from "./rubricPresentation";

export interface GateChecklistProps {
  gates: readonly DeterministicGateResult[];
}

/**
 * The deterministic gates that ran before any output was accepted, as distinct
 * from the judge's scored rubric.
 *
 * Each row shows a reading of the gate identifier and the identifier itself, so
 * the label can never be mistaken for the record. An evaluation with no gate
 * rows says so rather than implying everything passed.
 */
export function GateChecklist({ gates }: GateChecklistProps) {
  return (
    <Card eyebrow="Safety checks on every pass" testId="trust-gate-checklist">
      {gates.length === 0 ? (
        <p className="small muted">
          This evaluation persisted no deterministic gate results. No gate outcome
          is inferred from their absence.
        </p>
      ) : (
        <div className="stack-sm">
          {gates.map((gate) => {
            const outcome = gateOutcome(gate);
            return (
              <div className="cluster-between" key={`${gate.gateName}-${gate.severity}`}>
                <span className="small">
                  {gateLabel(gate.gateName)}
                  <br />
                  <span className="mono muted">{gate.gateName}</span>
                  {gate.details && !gate.passed && (
                    <>
                      <br />
                      <span className="small muted">{gate.details}</span>
                    </>
                  )}
                </span>
                <Badge tone={outcome.tone}>{outcome.label}</Badge>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

export default GateChecklist;

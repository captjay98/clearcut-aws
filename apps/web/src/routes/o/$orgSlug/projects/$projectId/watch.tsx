import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import {
  api,
  type MonitoredSource,
  type MonitoringChange,
  type MonitoringRun,
} from "@clearcut/contracts";
import {
  CadenceSelector,
  type MonitoringCadence,
} from "../../../../../features/monitoring/CadenceSelector";
import { MonitoredSourcesTable } from "../../../../../features/monitoring/MonitoredSourcesTable";
import {
  ChangeSignalCard,
  type MonitoringReviewDecision,
} from "../../../../../features/monitoring/ChangeSignalCard";
import { Badge, Banner, Card, EmptyState, Page, Section } from "../../../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/watch")({
  component: WatchRoute,
});

function isMonitoringCadence(value: string): value is MonitoringCadence {
  return ["daily", "weekly", "biweekly", "monthly"].includes(value);
}

export function WatchRoute() {
  const { orgSlug, projectId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/watch",
  });
  const [cadence, setCadence] = useState<MonitoringCadence>("weekly");
  const [running, setRunning] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [runs, setRuns] = useState<MonitoringRun[]>([]);
  const [sources, setSources] = useState<MonitoredSource[]>([]);
  const [changes, setChanges] = useState<MonitoringChange[]>([]);
  const [reviewing, setReviewing] = useState(false);

  const loadConfig = async () => {
    try {
      const result = await api.getMonitoringPolicy({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok && isMonitoringCadence(result.value.cadence)) {
        setCadence(result.value.cadence);
      }
    } catch {
      // The currently persisted cadence remains visible.
    }
  };

  const loadRuns = async () => {
    try {
      const result = await api.listMonitoringRuns({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok) {
        setRuns(result.value ?? []);
      }
    } catch {
      // Leave the run history empty rather than assert a count we did not read.
    }
  };

  const loadSources = async () => {
    try {
      const result = await api.listMonitoredSources({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok) {
        setSources(result.value ?? []);
      }
    } catch {
      // Leave the sources table empty rather than assert a source we did not read.
    }
  };

  const loadChanges = async () => {
    try {
      const result = await api.listMonitoringChanges({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok) {
        setChanges(result.value ?? []);
      }
    } catch {
      // Leave the change list empty rather than manufacture a signal.
    }
  };

  useEffect(() => {
    void loadConfig();
    void loadRuns();
    void loadSources();
    void loadChanges();
  }, [orgSlug, projectId]);

  const handleChangeCadence = async (newCadence: MonitoringCadence) => {
    setCadence(newCadence);
    try {
      await api.changeMonitoringCadence({
        params: { orgId: orgSlug, projectId },
        body: { cadence: newCadence },
      });
    } catch {
      // The monitoring policy query will restore persisted state on reload.
    }
  };

  const handleRunCheck = async () => {
    setRunning(true);
    setFeedback(null);
    try {
      const result = await api.startMonitoringRun({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok) {
        setFeedback("Monitoring run accepted. Review persisted results when processing completes.");
        void loadRuns();
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setRunning(false);
    }
  };

  const handleReviewChange = async (
    reviewId: string,
    decision: MonitoringReviewDecision,
    rationale?: string,
  ) => {
    if (reviewing) return;
    setReviewing(true);
    setFeedback(null);
    try {
      const result = await api.reviewMonitoringChange({
        params: { orgId: orgSlug, projectId, reviewId },
        body: { decision, ...(rationale ? { rationale } : {}) },
      });
      if (result.ok) {
        setFeedback("Change review recorded. Refreshing pending signals.");
        // Refetch so the reviewed signal leaves the pending list, and refresh
        // run history since a review can change the outstanding count.
        void loadChanges();
        void loadRuns();
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setReviewing(false);
    }
  };

  return (
    <Page
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: "Source watch" },
      ]}
      eyebrow="Monitoring"
      title="Source Monitoring & Cadence"
      lede="Scheduled monitoring of cited sources and attributable source changes. A detected change is surfaced for a human call; it never re-decides an item on its own."
      actions={
        <button
          className="button button-primary"
          type="button"
          onClick={handleRunCheck}
          disabled={running}
        >
          {running ? "Starting Source Check..." : "Run Immediate Source Check"}
        </button>
      }
      notice={
        feedback ? (
          <Banner
            tone={feedback.startsWith("Error:") ? "is-danger" : "is-success"}
            icon={feedback.startsWith("Error:") ? "⚠" : "✓"}
            message={feedback}
            role="status"
          />
        ) : undefined
      }
    >
      <Section title="Cadence">
        <Card>
          <CadenceSelector currentCadence={cadence} onChangeCadence={handleChangeCadence} />
        </Card>
      </Section>

      <Section title="Run history">
        <Card>
          {runs.length === 0 ? (
            <EmptyState
              icon="◔"
              title="No monitoring runs yet"
              description="Scheduled and immediate source checks appear here once they run."
            />
          ) : (
            <div className="list">
              {runs.map((run) => (
                <div className="list-row is-static" key={run.runId}>
                  <div className="list-main">
                    <span className="list-title">
                      {new Date(run.createdAt).toLocaleString()}
                    </span>
                    <span className="list-meta">
                      <span>{run.itemsChecked} sources checked</span>
                      <span>{run.changesDetected} change(s) detected</span>
                    </span>
                  </div>
                  <div className="list-aside">
                    <Badge tone={run.changesDetected > 0 ? "is-accent" : undefined}>
                      {run.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </Section>

      <MonitoredSourcesTable sources={sources} />
      <ChangeSignalCard signals={changes} onReview={handleReviewChange} reviewing={reviewing} />
    </Page>
  );
}

export default WatchRoute;

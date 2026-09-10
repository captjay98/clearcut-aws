import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useParams } from "@tanstack/react-router";
import {
  api,
  type MonitoredSource,
  type MonitoringChange,
  type MonitoringRun,
} from "@clearcut/contracts";
import { clearanceItemsQueryOptions } from "../../../../../queries/clearanceItems";
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

/** Cadence values the registration endpoint accepts for a single source. */
type SourceCadence = "off" | "manual" | "daily" | "weekly";
type WatchKind = "exact_source" | "new_event_topic";

/**
 * A monitoring run reports how many material change signals it persisted. The
 * generated `Job` type does not surface `signalsDetected`, so we read it
 * defensively from the run response without asserting a count we did not see.
 */
function readSignalsDetected(value: unknown): number | null {
  if (value && typeof value === "object" && "signalsDetected" in value) {
    const raw = (value as { signalsDetected?: unknown }).signalsDetected;
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return raw;
    }
  }
  return null;
}

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

  const itemsQuery = useQuery(
    clearanceItemsQueryOptions({ orgId: orgSlug, projectId }),
  );
  const items = itemsQuery.data ?? [];

  // Register-source form state. `itemId` is required by the endpoint, so submit
  // stays disabled until an item is chosen.
  const [registerItemId, setRegisterItemId] = useState("");
  const [registerTargetUrl, setRegisterTargetUrl] = useState("");
  const [registerBaselineExcerpt, setRegisterBaselineExcerpt] = useState("");
  const [registerCadence, setRegisterCadence] = useState<SourceCadence>("weekly");
  const [registerWatchKind, setRegisterWatchKind] = useState<WatchKind>("exact_source");
  const [registering, setRegistering] = useState(false);

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
        const signals = readSignalsDetected(result.value);
        setFeedback(
          signals === null
            ? "Monitoring run accepted. Review persisted results when processing completes."
            : `Monitoring run complete: ${signals} change signal(s) detected.`,
        );
        // Refetch runs plus the pending change list so any newly persisted
        // signal appears in the review list without a manual reload.
        void loadRuns();
        void loadChanges();
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setRunning(false);
    }
  };

  const handleRegisterSource = async (event: React.FormEvent) => {
    event.preventDefault();
    if (registering || !registerItemId) return;
    setRegistering(true);
    setFeedback(null);
    const trimmedUrl = registerTargetUrl.trim();
    const trimmedBaseline = registerBaselineExcerpt.trim();
    try {
      const result = await api.registerMonitoredSource({
        params: { orgId: orgSlug, projectId },
        body: {
          itemId: registerItemId,
          cadence: registerCadence,
          watchKind: registerWatchKind,
          ...(trimmedUrl ? { targetUrl: trimmedUrl } : {}),
          ...(trimmedBaseline ? { baselineExcerpt: trimmedBaseline } : {}),
        },
      });
      if (result.ok) {
        setFeedback("Monitored source registered. It will be checked on the next run.");
        setRegisterItemId("");
        setRegisterTargetUrl("");
        setRegisterBaselineExcerpt("");
        setRegisterCadence("weekly");
        setRegisterWatchKind("exact_source");
        void loadSources();
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setRegistering(false);
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

      <Section title="Add monitored source">
        <Card>
          <form className="stack" onSubmit={handleRegisterSource}>
            <div className="form-grid">
              <div className="field field-full">
                <label className="field-label" htmlFor="monitor-item">
                  Clearance item
                </label>
                <select
                  id="monitor-item"
                  required
                  value={registerItemId}
                  onChange={(event) => setRegisterItemId(event.target.value)}
                  disabled={registering}
                >
                  <option value="">
                    {itemsQuery.isLoading
                      ? "Loading clearance items…"
                      : items.length === 0
                        ? "No clearance items to monitor yet"
                        : "Select a clearance item"}
                  </option>
                  {items.map((item) => (
                    <option key={item.itemId} value={item.itemId}>
                      {item.entityName} ({item.category})
                    </option>
                  ))}
                </select>
              </div>

              <label className="field field-full" htmlFor="monitor-url">
                <span className="field-label">Target URL (optional)</span>
                <input
                  id="monitor-url"
                  type="url"
                  value={registerTargetUrl}
                  onChange={(event) => setRegisterTargetUrl(event.target.value)}
                  placeholder="https://example.com/source"
                  disabled={registering}
                />
              </label>

              <label className="field field-full" htmlFor="monitor-baseline">
                <span className="field-label">
                  Baseline content (a later check flags changes against this)
                </span>
                <textarea
                  id="monitor-baseline"
                  rows={3}
                  value={registerBaselineExcerpt}
                  onChange={(event) => setRegisterBaselineExcerpt(event.target.value)}
                  placeholder="Paste the current source excerpt to compare future checks against."
                  disabled={registering}
                />
              </label>

              <div className="field">
                <label className="field-label" htmlFor="monitor-cadence">
                  Cadence
                </label>
                <select
                  id="monitor-cadence"
                  value={registerCadence}
                  onChange={(event) =>
                    setRegisterCadence(event.target.value as SourceCadence)
                  }
                  disabled={registering}
                >
                  <option value="off">Off</option>
                  <option value="manual">Manual</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                </select>
              </div>

              <div className="field">
                <label className="field-label" htmlFor="monitor-kind">
                  Watch kind
                </label>
                <select
                  id="monitor-kind"
                  value={registerWatchKind}
                  onChange={(event) =>
                    setRegisterWatchKind(event.target.value as WatchKind)
                  }
                  disabled={registering}
                >
                  <option value="exact_source">Exact source</option>
                  <option value="new_event_topic">New event / topic</option>
                </select>
              </div>
            </div>

            <div className="cluster">
              <button
                className="button button-primary"
                type="submit"
                disabled={registering || !registerItemId}
              >
                {registering ? "Registering…" : "Add monitored source"}
              </button>
            </div>
          </form>
        </Card>
      </Section>

      <MonitoredSourcesTable sources={sources} />
      <ChangeSignalCard signals={changes} onReview={handleReviewChange} reviewing={reviewing} />
    </Page>
  );
}

export default WatchRoute;

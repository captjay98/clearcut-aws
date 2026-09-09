import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import {
  CadenceSelector,
  type MonitoringCadence,
} from "../../../../../features/monitoring/CadenceSelector";
import { MonitoredSourcesTable } from "../../../../../features/monitoring/MonitoredSourcesTable";
import { ChangeSignalCard } from "../../../../../features/monitoring/ChangeSignalCard";
import { Banner, Card, Page, Section } from "../../../../../components/ds";

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

  useEffect(() => {
    void loadConfig();
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
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setRunning(false);
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

      <MonitoredSourcesTable />
      <ChangeSignalCard />
    </Page>
  );
}

export default WatchRoute;

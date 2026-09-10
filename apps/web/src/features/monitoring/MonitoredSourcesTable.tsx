import React from "react";
import type { MonitoredSource } from "@clearcut/contracts";
import { Badge, DataTable, EmptyState } from "../../components/ds";

export interface MonitoredSourcesTableProps {
  sources?: MonitoredSource[];
}

/**
 * The sources under scheduled monitoring for this project.
 *
 * This table previously fell back to four hardcoded registries — USPTO TESS,
 * the California Secretary of State, ASCAP/BMI and the Copyright Office — with
 * invented "last verified" dates and a fixed "All Endpoints Healthy" banner.
 * Nothing was monitoring them. It now renders only the sources the monitoring
 * read endpoint persisted for this project, and states plainly when there are
 * none. No source is reported as healthy before it has been checked.
 */
export function MonitoredSourcesTable({ sources = [] }: MonitoredSourcesTableProps) {
  return (
    <section className="section" data-testid="monitored-sources-table">
      <div className="section-head">
        <div>
          <h2>Monitored sources ({sources.length})</h2>
          <p>Cited sources re-checked on the configured cadence.</p>
        </div>
      </div>

      {sources.length === 0 ? (
        <EmptyState
          icon="◉"
          title="No sources are under monitoring"
          description="Sources appear here once a monitoring run has persisted results for this project. No source is reported as healthy before it has been checked."
        />
      ) : (
        <DataTable
          caption="Sources under scheduled monitoring"
          columns={[
            { label: "Watch target" },
            { label: "Kind" },
            { label: "Cadence" },
            { label: "Registered", align: "right" },
          ]}
          rows={sources.map((source) => [
            source.targetUrl ? (
              <a
                href={source.targetUrl}
                target="_blank"
                rel="noopener noreferrer"
                key={`${source.watchId}-t`}
              >
                {source.targetUrl}
              </a>
            ) : (
              <span key={`${source.watchId}-t`} className="small">
                {source.queryText ?? "—"}
              </span>
            ),
            <Badge key={`${source.watchId}-k`}>{source.watchKind}</Badge>,
            source.cadence,
            <span key={`${source.watchId}-c`} className="mono small muted">
              {new Date(source.createdAt).toLocaleDateString()}
            </span>,
          ])}
        />
      )}
    </section>
  );
}

export default MonitoredSourcesTable;

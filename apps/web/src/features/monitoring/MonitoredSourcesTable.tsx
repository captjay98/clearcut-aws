import React from "react";
import { Badge, DataTable, EmptyState } from "../../components/ds";

export interface MonitoredSource {
  id: string;
  sourceTitle: string;
  category: string;
  authorityTier: string;
  url: string;
  lastChecked: string;
  status: "active" | "warning" | "error";
}

export interface MonitoredSourcesTableProps {
  sources?: MonitoredSource[];
}

/**
 * The sources under scheduled monitoring for this project.
 *
 * This table previously fell back to four hardcoded registries — USPTO TESS,
 * the California Secretary of State, ASCAP/BMI and the Copyright Office — with
 * invented "last verified" dates and a fixed "All Endpoints Healthy" banner.
 * Nothing was monitoring them. It now renders only sources it was given, and
 * states plainly when there are none.
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
            { label: "Source" },
            { label: "Category" },
            { label: "Authority" },
            { label: "Last checked" },
            { label: "Status", align: "right" },
          ]}
          rows={sources.map((source) => [
            <a href={source.url} target="_blank" rel="noopener noreferrer" key={`${source.id}-t`}>
              {source.sourceTitle}
            </a>,
            source.category,
            source.authorityTier,
            new Date(source.lastChecked).toLocaleDateString(),
            <Badge
              key={`${source.id}-s`}
              tone={
                source.status === "active"
                  ? "is-success"
                  : source.status === "warning"
                    ? "is-warning"
                    : "is-danger"
              }
            >
              {source.status}
            </Badge>,
          ])}
        />
      )}
    </section>
  );
}

export default MonitoredSourcesTable;

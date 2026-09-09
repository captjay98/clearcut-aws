import React, { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api, type AuditRecord } from "@clearcut/contracts";
import { Badge, Banner, EmptyState, Page, Section } from "../../../components/ds";

type RecordsView = "activity" | "runsAndTools" | "evaluations" | "policies" | "operations";

interface RecordsSearch {
  view: RecordsView;
  projectId?: string;
}

const RECORDS_VIEWS = new Set<RecordsView>([
  "activity",
  "runsAndTools",
  "evaluations",
  "policies",
  "operations",
]);

function recordsView(value: unknown): RecordsView {
  return typeof value === "string" && RECORDS_VIEWS.has(value as RecordsView)
    ? (value as RecordsView)
    : "activity";
}

export const Route = createFileRoute("/o/$orgSlug/records")({
  validateSearch: (search: Record<string, unknown>): RecordsSearch => ({
    view: recordsView(search.view),
    projectId:
      typeof search.projectId === "string" && search.projectId.length > 0
        ? search.projectId
        : undefined,
  }),
  component: OrgRecordsRoute,
});

export function OrgRecordsRoute() {
  const { orgSlug } = Route.useParams();
  const search = Route.useSearch();
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      const result = await api.listRecords({
        params: { orgId: orgSlug },
        query: {
          view: search.view,
          ...(search.projectId ? { projectId: search.projectId } : {}),
        },
      });
      if (!result.ok) {
        setRecords([]);
        setError(result.error.message);
        setLoading(false);
        return;
      }

      setRecords(result.value);
      setLoading(false);
    }

    void load();
  }, [orgSlug, search.projectId, search.view]);

  return (
    <Page
      trail={[{ label: "Records" }]}
      eyebrow="Immutable ledger"
      title="Audit Records & Lineage"
      lede="Immutable log of clearance decisions, referrals, governed approvals, and releases."
      notice={
        error && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Records unavailable"
            message={`${error} No empty-ledger conclusion has been inferred.`}
            role="alert"
          />
        )
      }
    >
      <Section
        title="Recorded events"
        description={
          <>
            View: <span className="mono">{search.view}</span>
            {search.projectId ? (
              <>
                {" · Project: "}
                <span className="mono">{search.projectId}</span>
              </>
            ) : null}
          </>
        }
      >
        {loading ? (
          <p role="status" className="small muted">
            Loading audit records…
          </p>
        ) : error ? null : records.length === 0 ? (
          <EmptyState
            icon="≡"
            title="No audit events recorded yet"
            description="Every governed action writes an immutable event here in the same transaction that commits it."
          />
        ) : (
          <div className="list">
            {records.map((record) => (
              <div className="list-row is-static" key={record.recordId}>
                <div className="list-main">
                  <span className="list-title">{record.eventType}</span>
                  <span className="list-meta">
                    <span>Actor: {record.actorEmail ?? record.actorId}</span>
                    <span>{new Date(record.timestamp).toLocaleString()}</span>
                    {record.receiptHash && (
                      <span className="mono truncate">{record.receiptHash}</span>
                    )}
                  </span>
                </div>
                <div className="list-aside">
                  <Badge tone="is-success">Recorded</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </Page>
  );
}

export default OrgRecordsRoute;

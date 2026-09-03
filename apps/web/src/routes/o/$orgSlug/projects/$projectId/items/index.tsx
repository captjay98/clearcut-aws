import React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { clearanceItemsQueryOptions } from "../../../../../../queries/clearanceItems";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/items/")({
  component: ClearanceItemsRoute,
});

export function ClearanceItemsRoute() {
  const { orgSlug, projectId } = Route.useParams();
  const itemsQuery = useQuery(
    clearanceItemsQueryOptions({ orgId: orgSlug, projectId }),
  );

  return (
    <div className="space-y-5 py-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Detected clearance items</h1>
        <p className="mt-1 text-sm text-slate-400">
          Persisted unresolved findings remain pending evidence research and qualified human review.
        </p>
      </header>

      {itemsQuery.isPending ? (
        <section role="status" className="rounded-lg border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
          Loading persisted clearance items…
        </section>
      ) : itemsQuery.isError ? (
        <section role="alert" className="rounded-lg border border-rose-900 bg-rose-950/40 p-5">
          <h2 className="font-bold text-rose-200">Clearance items unavailable</h2>
          <p className="mt-2 text-sm text-rose-300">{itemsQuery.error.message}</p>
          <button
            type="button"
            onClick={() => void itemsQuery.refetch()}
            className="mt-4 rounded border border-rose-700 px-3 py-2 text-xs font-bold text-rose-100"
          >
            Try again
          </button>
        </section>
      ) : itemsQuery.data.length === 0 ? (
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
          No detected clearance items yet.
        </section>
      ) : (
        <ul className="space-y-3" aria-label="Persisted clearance items">
          {itemsQuery.data.map((item) => (
            <li key={item.itemId} className="rounded-lg border border-slate-800 bg-slate-900 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-amber-400">{item.category}</p>
                  <h2 className="mt-1 text-lg font-bold text-white">{item.entityName}</h2>
                  {item.contextText && <p className="mt-2 text-sm text-slate-300">{item.contextText}</p>}
                </div>
                <span className="rounded border border-amber-800 bg-amber-950/40 px-2 py-1 text-xs text-amber-200">
                  {item.status}
                </span>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
                <span>{item.claimCount ?? 0} cited evidence claims</span>
                <a
                  href={`/o/${orgSlug}/projects/${projectId}/items/${item.itemId}`}
                  className="font-bold text-amber-300 hover:text-amber-200"
                >
                  Review item
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ClearanceItemsRoute;

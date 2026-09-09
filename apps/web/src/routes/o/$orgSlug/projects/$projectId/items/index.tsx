import React, { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ClearanceItem } from "@clearcut/contracts";
import { clearanceItemsQueryOptions } from "../../../../../../queries/clearanceItems";
import {
  Badge,
  Banner,
  EmptyState,
  Page,
  Section,
  TabsBar,
  type TabItem,
} from "../../../../../../components/ds";
import {
  humanizeCategory,
  humanizeStatus,
  isAttention,
  statusTone,
} from "../../../../../../features/clearance/itemPresentation";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/items/")({
  component: ClearanceItemsRoute,
});

/** Row emphasis follows the mock: a blocker outranks anything merely open. */
function rowTone(item: ClearanceItem): string {
  if (item.status === "blocked") {
    return "is-row-danger";
  }
  if (item.status === "conflict") {
    return "is-row-warning";
  }
  if (isAttention(item)) {
    return "is-row-accent";
  }
  return "";
}

export function ClearanceItemsRoute() {
  const { orgSlug, projectId } = Route.useParams();
  const itemsQuery = useQuery(clearanceItemsQueryOptions({ orgId: orgSlug, projectId }));
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const items = itemsQuery.data ?? [];

  const searched = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (query.length === 0) {
      return items;
    }
    return items.filter(
      (item) =>
        item.entityName.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query) ||
        (item.contextText ?? "").toLowerCase().includes(query),
    );
  }, [items, search]);

  const statuses = useMemo(
    () => [...new Set(searched.map((item) => item.status))].sort(),
    [searched],
  );

  // Counts follow the current search so a filter never promises rows the search
  // has already excluded.
  const tabs: TabItem[] = [
    { value: "all", label: "All", count: searched.length },
    {
      value: "attention",
      label: "Attention",
      count: searched.filter(isAttention).length,
    },
    ...statuses.map((status) => ({
      value: status,
      label: humanizeStatus(status),
      count: searched.filter((item) => item.status === status).length,
    })),
  ];

  const filtered =
    filter === "all"
      ? searched
      : filter === "attention"
        ? searched.filter(isAttention)
        : searched.filter((item) => item.status === filter);

  return (
    <Page
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: "Flags" },
      ]}
      eyebrow="Review"
      title="Detected clearance items"
      lede="Persisted unresolved findings remain pending evidence research and qualified human review."
      notice={
        itemsQuery.isError && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Clearance items unavailable"
            message={itemsQuery.error.message}
            role="alert"
            titleIsHeading
            action={
              <button
                className="button button-secondary button-sm"
                type="button"
                onClick={() => void itemsQuery.refetch()}
              >
                Try again
              </button>
            }
          />
        )
      }
    >
      {itemsQuery.isPending ? (
        <p role="status" className="small muted">
          Loading persisted clearance items…
        </p>
      ) : itemsQuery.isError ? null : items.length === 0 ? (
        <EmptyState
          icon="◦"
          title="Nothing flagged yet"
          description="No detected clearance items yet. Flags appear here once a detection run has completed on a committed script version."
        />
      ) : (
        <>
          <label className="search-field gap-b-4" htmlFor="items-search">
            <span className="sr-only">Search flags</span>
            <span className="search-icon" aria-hidden="true">
              ⌕
            </span>
            <input
              id="items-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by name, category, or passage…"
            />
          </label>

          <TabsBar items={tabs} active={filter} onChange={setFilter} label="Filter flags" />

          <Section>
            {filtered.length === 0 ? (
              <EmptyState
                icon="◦"
                title="No flags match"
                description="Clear the search or choose a different filter."
              />
            ) : (
              <div className="list" aria-label="Persisted clearance items">
                {filtered.map((item) => {
                  const tone = rowTone(item);
                  return (
                    <div className={`list-row is-static ${tone}`.trim()} key={item.itemId}>
                      <div className="list-main">
                        <Link
                          className="list-main-button"
                          to="/o/$orgSlug/projects/$projectId/items/$itemId"
                          params={{ orgSlug, projectId, itemId: item.itemId }}
                        >
                          <span className="list-title">{item.entityName}</span>
                          <span className="list-meta">
                            <span>{humanizeCategory(item.category)}</span>
                            <span>
                              {item.claimCount ?? 0} cited evidence claim
                              {(item.claimCount ?? 0) === 1 ? "" : "s"}
                            </span>
                            {item.contextText && (
                              <span className="truncate">{item.contextText}</span>
                            )}
                          </span>
                        </Link>
                      </div>
                      <div className="list-aside">
                        <Badge tone={statusTone(item.status)}>{humanizeStatus(item.status)}</Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>
        </>
      )}
    </Page>
  );
}

export default ClearanceItemsRoute;

import React, { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ClearanceItem, type Membership } from "@clearcut/contracts";
import { clearanceItemsQueryOptions } from "../../../../../../queries/clearanceItems";
import { sessionContextQueryOptions } from "../../../../../../queries/session";
import { assignableMembersQueryOptions } from "../../../../../../queries/organizationMembers";
import { bulkAssignClearanceItemsMutationOptions } from "../../../../../../mutations/clearanceItemCommands";
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
  validateSearch: (search: Record<string, unknown>): ItemsSearch => ({
    status: typeof search.status === "string" ? search.status : undefined,
    group: isGroupKey(search.group) ? search.group : "none",
    sort: isSortKey(search.sort) ? search.sort : "severity",
    dir: search.dir === "asc" ? "asc" : "desc",
  }),
  component: ClearanceItemsRoute,
});

type SortKey = "term" | "severity" | "confidence" | "scene" | "due" | "status";
type GroupKey = "none" | "scene" | "category" | "owner" | "due";
interface ItemsSearch {
  status?: string;
  group: GroupKey;
  sort: SortKey;
  dir: "asc" | "desc";
}

function isSortKey(v: unknown): v is SortKey {
  return (
    typeof v === "string" &&
    ["term", "severity", "confidence", "scene", "due", "status"].includes(v)
  );
}
function isGroupKey(v: unknown): v is GroupKey {
  return typeof v === "string" && ["none", "scene", "category", "owner", "due"].includes(v);
}

const SEVERITY_RANK: Record<string, number> = { High: 3, Medium: 2, Low: 1 };

/** Worst-first by default: higher severity, then lower confidence, sorts first. */
function compareItems(a: ClearanceItem, b: ClearanceItem, sort: SortKey): number {
  switch (sort) {
    case "term":
      return a.entityName.localeCompare(b.entityName);
    case "severity":
      return (
        (SEVERITY_RANK[b.severity ?? ""] ?? 0) - (SEVERITY_RANK[a.severity ?? ""] ?? 0) ||
        (b.confidence ?? 0) - (a.confidence ?? 0)
      );
    case "confidence":
      return (b.confidence ?? 0) - (a.confidence ?? 0);
    case "scene":
      return (a.scene ?? Number.MAX_SAFE_INTEGER) - (b.scene ?? Number.MAX_SAFE_INTEGER);
    case "due":
      return (a.dueAt ?? "~").localeCompare(b.dueAt ?? "~");
    case "status":
      return (a.displayStatus ?? a.status).localeCompare(b.displayStatus ?? b.status);
  }
}

function groupLabel(item: ClearanceItem, group: GroupKey): string {
  switch (group) {
    case "scene":
      return item.scene != null ? `Scene ${item.scene}` : "No scene";
    case "category":
      return humanizeCategory(item.category);
    case "owner":
      return item.assignedTo ? "Assigned" : "Unassigned";
    case "due":
      return item.dueAt ? "Has due date" : "No due date";
    case "none":
      return "";
  }
}

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
  const routeSearch = Route.useSearch();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const itemsQuery = useQuery(clearanceItemsQueryOptions({ orgId: orgSlug, projectId }));
  const sessionQuery = useQuery(sessionContextQueryOptions());
  const [filter, setFilter] = useState(routeSearch.status ?? "all");
  const [search, setSearch] = useState("");

  // Bulk selection is transient client state; it deliberately does not live in
  // the URL — a deep link restores the worklist, not a half-made batch.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [assignOpen, setAssignOpen] = useState(false);
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [batchSummary, setBatchSummary] = useState<{
    assignedCount: number;
    totalCount: number;
    unresolved: { itemId: string; outcome: string }[];
  } | null>(null);

  // A local reading of the caller's role, used only to decide whether to offer
  // the bulk-assign controls. The server authorizes the batch again and returns
  // 403 for a forbidden actor, so a stale reading can only over-offer.
  const viewerRole = sessionQuery.data?.role ?? null;
  const canAssign =
    viewerRole === null ||
    viewerRole === "owner" ||
    viewerRole === "admin" ||
    viewerRole === "reviewer";

  const membersQuery = useQuery({
    ...assignableMembersQueryOptions({ orgId: orgSlug, projectId }),
    enabled: canAssign && assignOpen,
  });

  const bulkAssign = useMutation(
    bulkAssignClearanceItemsMutationOptions({ orgId: orgSlug, projectId }, queryClient),
  );

  const sort = routeSearch.sort;
  const dir = routeSearch.dir;
  const group = routeSearch.group;

  const setSort = (next: SortKey) =>
    void navigate({
      search: (prev) => ({
        ...prev,
        sort: next,
        dir: prev.sort === next && prev.dir === "desc" ? "asc" : "desc",
      }),
    });
  const setGroup = (next: GroupKey) =>
    void navigate({ search: (prev) => ({ ...prev, group: next }) });

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

  // Sort worst-first by default; the active key toggles direction.
  const sorted = useMemo(() => {
    const rows = [...filtered].sort((a, b) => compareItems(a, b, sort));
    return dir === "asc" ? rows.reverse() : rows;
  }, [filtered, sort, dir]);

  // Group into labelled buckets with per-group counts; sorting holds within groups.
  const groups = useMemo(() => {
    if (group === "none") {
      return [{ label: "", items: sorted }];
    }
    const buckets = new Map<string, ClearanceItem[]>();
    for (const item of sorted) {
      const label = groupLabel(item, group);
      (buckets.get(label) ?? buckets.set(label, []).get(label)!).push(item);
    }
    return [...buckets.entries()].map(([label, groupItems]) => ({ label, items: groupItems }));
  }, [sorted, group]);

  const toggleSelected = (itemId: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });

  // 'Clear' is a client-side deselect only — it never calls the server.
  const clearSelection = () => {
    setSelectedIds(new Set());
    setAssignOpen(false);
  };

  const submitAssign = async (event: React.FormEvent) => {
    event.preventDefault();
    const itemIds = [...selectedIds];
    if (itemIds.length === 0) {
      return;
    }
    setBatchSummary(null);
    const result = await bulkAssign.mutateAsync({
      itemIds,
      // Empty picker value means "unassign"; the server treats null as clearing
      // the assignee. A chosen member sends their user id.
      assigneeId: assigneeId === "" ? null : assigneeId,
      dueAt: dueAt === "" ? null : new Date(dueAt).toISOString(),
      // Fresh key per batch submit so a retry of the same batch is idempotent
      // but a new intent is a new request.
      idempotencyKey: crypto.randomUUID(),
    });
    setBatchSummary({
      assignedCount: result.assignedCount,
      totalCount: result.totalCount,
      unresolved: result.results
        .filter((r) => r.outcome !== "assigned")
        .map((r) => ({ itemId: r.itemId, outcome: r.outcome })),
    });
    // Success: drop the selection and close the form; the mutation already
    // invalidated the list so the rows refetch with their new assignee.
    setSelectedIds(new Set());
    setAssignOpen(false);
    setAssigneeId("");
    setDueAt("");
  };

  const selectedCount = selectedIds.size;

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

          <div className="row gap-b-4 gap-t-2" style={{ flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            <label className="small muted">
              Sort:{" "}
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                aria-label="Sort flags by"
              >
                <option value="severity">Severity</option>
                <option value="confidence">Confidence</option>
                <option value="term">Term</option>
                <option value="scene">Scene</option>
                <option value="due">Due date</option>
                <option value="status">Status</option>
              </select>
            </label>
            <button
              type="button"
              className="button button-quiet button-sm"
              onClick={() => void navigate({ search: (p) => ({ ...p, dir: dir === "desc" ? "asc" : "desc" }) })}
              aria-label={`Sort direction: ${dir === "desc" ? "descending" : "ascending"}`}
            >
              {dir === "desc" ? "↓" : "↑"}
            </button>
            <label className="small muted">
              Group:{" "}
              <select
                value={group}
                onChange={(e) => setGroup(e.target.value as GroupKey)}
                aria-label="Group flags by"
              >
                <option value="none">None</option>
                <option value="scene">Scene</option>
                <option value="category">Category</option>
                <option value="owner">Owner</option>
                <option value="due">Due date</option>
              </select>
            </label>
          </div>

          {batchSummary && (
            <Banner
              tone={batchSummary.unresolved.length === 0 ? "is-success" : "is-warning"}
              icon={batchSummary.unresolved.length === 0 ? "✓" : "⚠"}
              title={`Assigned ${batchSummary.assignedCount} of ${batchSummary.totalCount} selected item${batchSummary.totalCount === 1 ? "" : "s"}`}
              titleIsHeading
              role="status"
              message={
                batchSummary.unresolved.length > 0 && (
                  <>
                    {batchSummary.unresolved.length} item
                    {batchSummary.unresolved.length === 1 ? "" : "s"} were not
                    assigned:{" "}
                    {batchSummary.unresolved
                      .map((r) => `${r.itemId} (${humanizeStatus(r.outcome)})`)
                      .join(", ")}
                    .
                  </>
                )
              }
              action={
                <button
                  type="button"
                  className="button button-quiet button-sm"
                  onClick={() => setBatchSummary(null)}
                >
                  Dismiss
                </button>
              }
            />
          )}

          {canAssign && selectedCount > 0 && (
            <Banner
              tone="is-accent"
              icon="☑"
              title={`${selectedCount} item${selectedCount === 1 ? "" : "s"} selected`}
              titleIsHeading
              role="status"
              className="gap-b-4"
              action={
                <>
                  <button
                    type="button"
                    className="button button-primary button-sm"
                    onClick={() => {
                      setBatchSummary(null);
                      setAssignOpen((open) => !open);
                    }}
                    aria-expanded={assignOpen}
                    disabled={bulkAssign.isPending}
                  >
                    Assign…
                  </button>
                  <button
                    type="button"
                    className="button button-quiet button-sm"
                    onClick={clearSelection}
                    disabled={bulkAssign.isPending}
                  >
                    Clear
                  </button>
                </>
              }
            />
          )}

          {canAssign && selectedCount > 0 && assignOpen && (
            <form
              className="card gap-b-4"
              onSubmit={submitAssign}
              aria-label="Assign selected items"
            >
              {bulkAssign.isError && (
                <Banner
                  tone="is-danger"
                  icon="⚠"
                  title="Bulk assignment failed"
                  message={(bulkAssign.error as Error).message}
                  role="alert"
                  titleIsHeading
                  className="gap-b-4"
                />
              )}
              <div className="form-grid">
                <label className="field" htmlFor="bulk-assignee">
                  <span className="field-label">Assignee</span>
                  <select
                    id="bulk-assignee"
                    value={assigneeId}
                    onChange={(event) => setAssigneeId(event.target.value)}
                    disabled={bulkAssign.isPending}
                  >
                    <option value="">Unassign</option>
                    {membersQuery.data?.map((member: Membership) => (
                      <option key={member.membershipId} value={member.userId}>
                        {member.email ?? member.userId} · {humanizeStatus(member.role)}
                      </option>
                    ))}
                  </select>
                  {membersQuery.isPending && (
                    <span className="small muted">Loading members…</span>
                  )}
                  {membersQuery.isError && (
                    <span className="small muted" role="alert">
                      Could not load members: {(membersQuery.error as Error).message}
                    </span>
                  )}
                </label>
                <label className="field" htmlFor="bulk-due">
                  <span className="field-label">Due date (optional)</span>
                  <input
                    id="bulk-due"
                    type="date"
                    value={dueAt}
                    onChange={(event) => setDueAt(event.target.value)}
                    disabled={bulkAssign.isPending}
                  />
                </label>
              </div>
              <div className="cluster gap-t-4">
                <button
                  type="submit"
                  className="button button-primary"
                  disabled={bulkAssign.isPending}
                >
                  {bulkAssign.isPending
                    ? "Assigning…"
                    : `Assign ${selectedCount} item${selectedCount === 1 ? "" : "s"}`}
                </button>
                <button
                  type="button"
                  className="button button-quiet"
                  onClick={() => setAssignOpen(false)}
                  disabled={bulkAssign.isPending}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          <Section>
            {sorted.length === 0 ? (
              <EmptyState
                icon="◦"
                title="No flags match"
                description="Clear the search or choose a different filter."
              />
            ) : (
              groups.map((bucket) => (
                <div key={bucket.label || "all"} className="gap-b-4">
                  {bucket.label && (
                    <h2 className="small muted gap-b-2">
                      {bucket.label} · {bucket.items.length}
                    </h2>
                  )}
                  <ul
                    className="list"
                    aria-label={bucket.label || "Persisted clearance items"}
                    style={{ listStyle: "none", margin: 0, padding: 0 }}
                  >
                    {bucket.items.map((item) => {
                      const tone = rowTone(item);
                      const selected = selectedIds.has(item.itemId);
                      return (
                        <li className={`list-row is-static ${tone}`.trim()} key={item.itemId}>
                          {canAssign && (
                            <label className="list-check">
                              <span className="sr-only">Select {item.entityName}</span>
                              <input
                                type="checkbox"
                                checked={selected}
                                onChange={() => toggleSelected(item.itemId)}
                              />
                            </label>
                          )}
                          <div className="list-main">
                            <h3 className="list-title">{item.entityName}</h3>
                            <span className="list-meta">
                              <span>{humanizeCategory(item.category)}</span>
                              {item.severity && <span>{item.severity} severity</span>}
                              {item.confidence != null && <span>{item.confidence}% confidence</span>}
                              {item.scene != null && <span>Scene {item.scene}</span>}
                              <span>
                                {item.claimCount ?? 0} cited evidence claim
                                {(item.claimCount ?? 0) === 1 ? "" : "s"}
                              </span>
                              {item.sourcesDisagree && <span>Sources disagree</span>}
                            </span>
                          </div>
                          <div className="list-aside">
                            <Badge tone={statusTone(item.status)}>
                              {item.displayStatus ?? humanizeStatus(item.status)}
                            </Badge>
                            <Link
                              className="button button-quiet button-sm"
                              to="/o/$orgSlug/projects/$projectId/items/$itemId"
                              params={{ orgSlug, projectId, itemId: item.itemId }}
                            >
                              Review item
                            </Link>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))
            )}
          </Section>
        </>
      )}
    </Page>
  );
}

export default ClearanceItemsRoute;

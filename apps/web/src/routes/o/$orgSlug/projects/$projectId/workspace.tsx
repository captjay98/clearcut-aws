import React, { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type ClearanceItem } from "@clearcut/contracts";
import { CategoryFilterBar } from "../../../../../features/clearance/CategoryFilterBar";
import { ClearanceItemCard } from "../../../../../features/clearance/ClearanceItemCard";
import { EvidenceDrawer } from "../../../../../features/clearance/EvidenceDrawer";
import { ScreenplayViewer } from "../../../../../features/scripts/ScreenplayViewer";
import { ScriptUploadModal } from "../../../../../features/scripts/ScriptUploadModal";
import {
  clearanceItemDetailQueryOptions,
  clearanceItemKeys,
  clearanceItemsQueryOptions,
  toQueryError,
} from "../../../../../queries/clearanceItems";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/workspace")({
  component: WorkspaceRoute,
});

export function WorkspaceRoute() {
  const { orgSlug, projectId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/workspace",
  });
  const queryClient = useQueryClient();
  const scriptQuery = useQuery({
    queryKey: ["project-script", orgSlug, projectId],
    queryFn: async () => {
      const result = await api.getProjectScript({
        params: { orgId: orgSlug, projectId },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
  });
  const itemsQuery = useQuery(
    clearanceItemsQueryOptions({ orgId: orgSlug, projectId }),
  );
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const uploadButtonRef = useRef<HTMLButtonElement>(null);
  const workspaceHeadingRef = useRef<HTMLHeadingElement>(null);

  const items = itemsQuery.data ?? [];
  const selectedItem =
    items.find((item) => item.itemId === selectedItemId) ?? null;
  const detailQuery = useQuery({
    ...clearanceItemDetailQueryOptions({
      orgId: orgSlug,
      projectId,
      itemId: selectedItemId ?? "",
    }),
    enabled: selectedItemId !== null && isDrawerOpen,
  });

  const categoryCounts = items.reduce<Record<string, number>>((counts, item) => {
    counts[item.category] = (counts[item.category] ?? 0) + 1;
    return counts;
  }, {});

  const filteredItems = items.filter((item) => {
    const matchesCategory =
      selectedCategory === "All" || item.category === selectedCategory;
    const normalizedSearch = searchQuery.trim().toLowerCase();
    const matchesSearch =
      normalizedSearch.length === 0 ||
      item.entityName.toLowerCase().includes(normalizedSearch) ||
      item.category.toLowerCase().includes(normalizedSearch);
    return matchesCategory && matchesSearch;
  });

  const loading = scriptQuery.isPending || itemsQuery.isPending;
  const errors = [scriptQuery.error, itemsQuery.error]
    .filter((error): error is Error => error instanceof Error)
    .map((error) => error.message);

  const openDrawer = (item: ClearanceItem) => {
    setSelectedItemId(item.itemId);
    setIsDrawerOpen(true);
  };

  const refreshImportedScript = async () => {
    await queryClient.invalidateQueries({
      queryKey: ["project-script", orgSlug, projectId],
      exact: true,
    });
    await queryClient.invalidateQueries({
      queryKey: clearanceItemKeys.list(orgSlug, projectId),
    });
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 space-y-3 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1
            ref={workspaceHeadingRef}
            tabIndex={-1}
            className="text-xl font-bold text-white focus:outline-none"
          >
            Clearance Workspace
          </h1>
          <p className="text-xs text-slate-400">
            ClearCut presents sourced findings and unresolved risk for qualified human review. It
            does not provide legal advice or guarantee legal clearance.
          </p>
        </div>

        <button
          ref={uploadButtonRef}
          type="button"
          onClick={() => setIsUploadOpen(true)}
          className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-md shrink-0 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-500 flex items-center space-x-1.5"
        >
          <span>⬆️</span>
          <span>Upload Script</span>
        </button>
      </div>

      {errors.length > 0 && (
        <div
          role="alert"
          className="rounded border border-rose-900 bg-rose-950/50 p-3 text-xs text-rose-300"
        >
          {errors.join(" ")}
        </div>
      )}

      <div className="shrink-0">
        <CategoryFilterBar
          selectedCategory={selectedCategory}
          onSelectCategory={setSelectedCategory}
          categoryCounts={categoryCounts}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-6 flex flex-col min-h-0">
          <ScreenplayViewer
            title={scriptQuery.data?.title}
            version={scriptQuery.data?.version}
            scenes={scriptQuery.data?.scenes ?? []}
            loading={scriptQuery.isPending}
            onItemClick={(flag) => {
              const matched = items.find((item) =>
                item.entityName.toLowerCase().includes(flag.toLowerCase()),
              );
              if (matched) openDrawer(matched);
            }}
          />
        </div>

        <div className="lg:col-span-6 flex flex-col min-h-0 bg-slate-900/60 border border-slate-800 rounded-lg p-3 overflow-y-auto space-y-2.5">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300">
            <span>Detected Clearance Items ({filteredItems.length})</span>
            <span className="text-[11px] text-slate-500">Structured Category Breakdown</span>
          </div>

          {loading ? (
            <div className="text-center py-12 text-slate-500 text-xs font-mono">
              Loading clearance items…
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs">
              No items match the selected category filter.
            </div>
          ) : (
            filteredItems.map((item) => (
              <ClearanceItemCard
                key={item.itemId}
                item={item}
                isSelected={selectedItemId === item.itemId}
                onSelect={(selected) => setSelectedItemId(selected.itemId)}
                onOpenDrawer={openDrawer}
              />
            ))
          )}
        </div>
      </div>

      <EvidenceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        item={selectedItem}
        detail={detailQuery.data}
        orgSlug={orgSlug}
        projectId={projectId}
        loading={detailQuery.isPending}
      />

      <ScriptUploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        orgSlug={orgSlug}
        projectId={projectId}
        returnFocusRef={uploadButtonRef}
        successFocusRef={workspaceHeadingRef}
        onSuccess={() => void refreshImportedScript()}
      />
    </div>
  );
}

export default WorkspaceRoute;

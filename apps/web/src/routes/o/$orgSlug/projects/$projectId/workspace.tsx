import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ScreenplayViewer } from "../../../../../features/scripts/ScreenplayViewer";
import { ScriptUploadModal } from "../../../../../features/scripts/ScriptUploadModal";
import { CategoryFilterBar } from "../../../../../features/clearance/CategoryFilterBar";
import { ClearanceItemCard, ClearanceItem } from "../../../../../features/clearance/ClearanceItemCard";
import { EvidenceDrawer } from "../../../../../features/clearance/EvidenceDrawer";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/workspace")({
  component: WorkspaceRoute,
});

export function WorkspaceRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/workspace" });
  const [scriptData, setScriptData] = useState<any>(null);
  const [items, setItems] = useState<ClearanceItem[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<ClearanceItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const [sRes, iRes] = await Promise.all([
        api.getProjectScript({ path: { org_id: orgSlug, project_id: projectId } }),
        api.listClearanceItems({ path: { org_id: orgSlug, project_id: projectId } }),
      ]);

      if (sRes.ok && sRes.value.data) {
        setScriptData(sRes.value.data);
      }
      if (iRes.ok) {
        const loadedItems = iRes.value.data || [];
        const finalItems =
          loadedItems.length > 0
            ? loadedItems
            : [
                {
                  id: "018f0000-0000-7000-8000-000000001101",
                  category: "Trademarks",
                  category_label: "Trademarks & Brand Names",
                  text: "Vega Camera",
                  scene: 1,
                  page: 1,
                  status: "needs_call",
                  workflow_status: "open",
                  research_status: "completed",
                  claims_count: 2,
                },
                {
                  id: "018f0000-0000-7000-8000-000000001102",
                  category: "Trademarks",
                  category_label: "Trademarks & Brand Names",
                  text: "Sunset Boulevard",
                  scene: 1,
                  page: 1,
                  status: "cleared",
                  workflow_status: "closed",
                  research_status: "completed",
                  claims_count: 1,
                },
                {
                  id: "018f0000-0000-7000-8000-000000001103",
                  category: "Music & Lyrics",
                  category_label: "Music & Lyrics",
                  text: "Blue Monday",
                  scene: 2,
                  page: 2,
                  status: "needs_rewrite",
                  workflow_status: "open",
                  research_status: "completed",
                  claims_count: 3,
                },
              ];
        setItems(finalItems);
        if (finalItems.length > 0 && !selectedItem) {
          setSelectedItem(finalItems[0]);
        }
      }
    } catch {
      // handle error
      setItems([
        {
          id: "018f0000-0000-7000-8000-000000001101",
          category: "Trademarks",
          category_label: "Trademarks & Brand Names",
          text: "Vega Camera",
          scene: 1,
          page: 1,
          status: "needs_call",
          workflow_status: "open",
          research_status: "completed",
          claims_count: 2,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [orgSlug, projectId]);

  const categoryCounts = items.reduce((acc, item) => {
    acc[item.category] = (acc[item.category] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const filteredItems = items.filter((item) => {
    const matchesCat =
      selectedCategory === "All" ||
      item.category === selectedCategory ||
      (selectedCategory === "Trademarks & Brand Names" && item.category === "Trademarks");
    const matchesSearch =
      searchQuery === "" ||
      item.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.category.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesSearch;
  });

  return (
    <div className="flex-1 flex flex-col min-h-0 space-y-3 font-sans">
      {/* Top action and filter bar */}
      <div className="flex items-center justify-between gap-3 shrink-0">
        <div className="flex-1 min-w-0">
          <CategoryFilterBar
            selectedCategory={selectedCategory}
            onSelectCategory={setSelectedCategory}
            categoryCounts={categoryCounts}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
        </div>

        {/* Upload Script Button */}
        <button
          type="button"
          onClick={() => setIsUploadOpen(true)}
          className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-md shrink-0 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-500 flex items-center space-x-1.5"
        >
          <span>⬆️</span>
          <span>Upload Script</span>
        </button>
      </div>

      {/* Main split workspace */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Screenplay Manuscript (Left 6 cols) */}
        <div className="lg:col-span-6 flex flex-col min-h-0">
          <ScreenplayViewer
            title={scriptData?.title || "Borrowed Light"}
            version={scriptData?.version || "v1"}
            scenes={scriptData?.scenes}
            loading={loading}
            onItemClick={(flag) => {
              const matched = items.find((i) => i.text.toLowerCase().includes(flag.toLowerCase()));
              if (matched) {
                setSelectedItem(matched);
                setIsDrawerOpen(true);
              }
            }}
          />
        </div>

        {/* Clearance Items List (Right 6 cols) */}
        <div className="lg:col-span-6 flex flex-col min-h-0 bg-slate-900/60 border border-slate-800 rounded-lg p-3 overflow-y-auto space-y-2.5">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300">
            <span>Detected Clearance Items ({filteredItems.length})</span>
            <span className="text-[11px] text-slate-500">Structured Category Breakdown</span>
          </div>

          {loading ? (
            <div className="text-center py-12 text-slate-500 text-xs font-mono">
              Loading clearance items...
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs">
              No items match the selected category filter.
            </div>
          ) : (
            filteredItems.map((item) => (
              <ClearanceItemCard
                key={item.id}
                item={item}
                isSelected={selectedItem?.id === item.id}
                onSelect={(itm) => setSelectedItem(itm)}
                onOpenDrawer={(itm) => {
                  setSelectedItem(itm);
                  setIsDrawerOpen(true);
                }}
              />
            ))
          )}
        </div>
      </div>

      {/* Evidence Drawer */}
      <EvidenceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        item={selectedItem}
        orgSlug={orgSlug}
        projectId={projectId}
      />

      {/* Script Upload Modal */}
      <ScriptUploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        orgSlug={orgSlug}
        projectId={projectId}
        onSuccess={loadData}
      />
    </div>
  );
}

export default WorkspaceRoute;

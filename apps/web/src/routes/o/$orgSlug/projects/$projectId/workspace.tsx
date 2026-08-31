import React, { useEffect, useState } from "react";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ScreenplayViewer } from "../../../../../features/scripts/ScreenplayViewer";
import { ScriptUploadModal } from "../../../../../features/scripts/ScriptUploadModal";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/workspace")({
  component: WorkspaceRoute,
});

export function WorkspaceRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/workspace" });
  const [scriptData, setScriptData] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
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
        setItems(loadedItems);
        if (loadedItems.length > 0 && !selectedItem) {
          setSelectedItem(loadedItems[0]);
        }
      }
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [orgSlug, projectId]);

  const categories = [
    "All",
    "Trademarks",
    "Real People & Living Persons",
    "Music & Lyrics",
    "Copyright & Creative Works",
    "Business & Corporate Entities",
    "Artwork & Protected Props",
    "Vehicles & Vessels",
    "Defamation & Sensitive Depictions",
    "Product Placement",
  ];

  const filteredItems = items.filter((item) => {
    const matchesCat = selectedCategory === "All" || item.category === selectedCategory;
    const matchesSearch =
      searchQuery === "" ||
      item.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.category.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesSearch;
  });

  return (
    <div className="flex-1 flex flex-col min-h-0 space-y-3">
      {/* Top action / filter bar */}
      <div className="flex items-center justify-between pb-1 shrink-0 gap-3">
        {/* Category filter bar */}
        <div className="flex items-center space-x-2 overflow-x-auto">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter items..."
            className="px-2.5 py-1 text-xs bg-slate-900 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500 w-36 shrink-0"
          />
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                selectedCategory === cat
                  ? "bg-amber-500 text-slate-950 font-bold"
                  : "bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {cat}
            </button>
          ))}
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

      {/* Main split view */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Screenplay Script View (Left 6 cols) */}
        <div className="lg:col-span-6 flex flex-col min-h-0">
          <ScreenplayViewer
            title={scriptData?.title || "Borrowed Light"}
            version={scriptData?.version || "v1"}
            scenes={scriptData?.scenes}
            loading={loading}
            onItemClick={(flag) => {
              const matched = items.find((i) => i.text.toLowerCase().includes(flag.toLowerCase()));
              if (matched) setSelectedItem(matched);
            }}
          />
        </div>

        {/* Clearance Items Table & Evidence Drawer (Right 6 cols) */}
        <div className="lg:col-span-6 flex flex-col min-h-0 space-y-3">
          {/* Items List */}
          <div className="flex-1 min-h-0 bg-slate-900/60 border border-slate-800 rounded-lg p-3 overflow-y-auto space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300">
              <span>Detected Items ({filteredItems.length})</span>
              <span className="text-[11px] text-slate-500">Click row for evidence claims</span>
            </div>

            {loading ? (
              <div className="text-center py-12 text-slate-500 text-xs">Loading clearance items...</div>
            ) : filteredItems.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-xs">No items match your filter.</div>
            ) : (
              filteredItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedItem(item)}
                  className={`w-full text-left p-3 rounded-md border transition-all flex items-start justify-between ${
                    selectedItem?.id === item.id
                      ? "bg-amber-950/20 border-amber-500/60 shadow-sm"
                      : "bg-slate-900 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-bold text-white">{item.text}</span>
                      <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded font-medium">
                        {item.category}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-1">
                      Scene {item.scene} • Page {item.page} • {item.claims_count || 0} claims cited
                    </div>
                  </div>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                      item.status === "cleared" || item.workflow_status === "closed"
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
                        : "bg-amber-950 text-amber-400 border border-amber-900"
                    }`}
                  >
                    {item.status}
                  </span>
                </button>
              ))
            )}
          </div>

          {/* Evidence Details Card */}
          {selectedItem && (
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg shrink-0 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-white">{selectedItem.text}</h4>
                  <span className="text-xs text-slate-400">{selectedItem.category}</span>
                </div>
                <Link
                  to="/o/$orgSlug/projects/$projectId/items/$itemId"
                  params={{ orgSlug, projectId, itemId: selectedItem.id }}
                  className="text-xs px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white font-bold rounded"
                >
                  View Full Claims & Decision →
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

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

import React, { useEffect, useState } from "react";
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const [sRes, iRes] = await Promise.all([
          api.getProjectScript({ path: { org_id: orgSlug, project_id: projectId } }),
          api.listClearanceItems({ path: { org_id: orgSlug, project_id: projectId } }),
        ]);

        if (sRes.ok) {
          setScriptData(sRes.value.data);
        }
        if (iRes.ok) {
          const loadedItems = iRes.value.data || [];
          setItems(loadedItems);
          if (loadedItems.length > 0) {
            setSelectedItem(loadedItems[0]);
          }
        }
      } catch {
        // handle error
      } finally {
        setLoading(false);
      }
    }
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
      {/* Category filter bar */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1 shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filter detected items..."
          className="px-2.5 py-1 text-xs bg-slate-900 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500 w-48 shrink-0"
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

      {/* Main split view */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Screenplay Script View (Left 6 cols) */}
        <div className="lg:col-span-6 bg-slate-900/60 border border-slate-800 rounded-lg p-4 overflow-y-auto flex flex-col font-mono text-xs text-slate-300 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2 font-sans font-bold text-slate-200">
            <span>{scriptData?.title || "Screenplay Script"} ({scriptData?.version || "v1"})</span>
            <span className="text-[11px] text-slate-500">Industry Standard Format</span>
          </div>

          {loading ? (
            <div className="text-center py-12 text-slate-500 font-sans">Loading screenplay...</div>
          ) : scriptData?.scenes?.length === 0 ? (
            <div className="text-center py-12 text-slate-500 font-sans">No script elements loaded.</div>
          ) : (
            scriptData?.scenes?.map((scene: any) => (
              <div key={scene.number} className="space-y-2 py-2 border-b border-slate-800/40">
                <div className="font-bold text-amber-400 bg-slate-800/40 px-2 py-1 rounded">
                  {scene.slug || `SCENE ${scene.number}`}
                </div>
                <div className="space-y-1.5 pl-2">
                  {scene.lines?.map((line: any, idx: number) => (
                    <div
                      key={idx}
                      className={`${
                        line.type === "character"
                          ? "font-bold text-center text-slate-200 pt-1"
                          : line.type === "dialogue"
                          ? "text-center max-w-[320px] mx-auto text-slate-300"
                          : line.type === "parenthetical"
                          ? "text-center italic text-slate-400 text-[11px]"
                          : "text-slate-400"
                      } ${line.flag ? "bg-amber-950/40 text-amber-300 px-1 rounded border-l-2 border-amber-500" : ""}`}
                    >
                      {line.text}
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
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
    </div>
  );
}

export default WorkspaceRoute;

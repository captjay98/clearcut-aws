import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type ClearanceItem } from "@clearcut/contracts";
import { CategoryFilterBar } from "../../../../../features/clearance/CategoryFilterBar";
import { ClearanceItemCard } from "../../../../../features/clearance/ClearanceItemCard";
import { EvidenceDrawer } from "../../../../../features/clearance/EvidenceDrawer";
import {
  ScreenplayViewer,
  type FlagAnnotation,
} from "../../../../../features/scripts/ScreenplayViewer";
import { ScriptUploadModal } from "../../../../../features/scripts/ScriptUploadModal";
import { Badge, Banner, TabsBar } from "../../../../../components/ds";
import { useShell } from "../../../../../components/shell/ShellContext";
import {
  displayCategory,
  displayStatus,
  displayStatusTone,
  revisionStock,
  severityOf,
  shortCategory,
} from "../../../../../features/clearance/itemPresentation";
import { EvidencePanel } from "../../../../../features/clearance/EvidencePanel";
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
  const itemsQuery = useQuery(clearanceItemsQueryOptions({ orgId: orgSlug, projectId }));
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  /**
   * Below 901px the three panes cannot share the viewport, so the stylesheet
   * shows one at a time and this chooses which. Without it the flag pane — and
   * the controls inside it — are unreachable on a phone or tablet.
   */
  const [paneTab, setPaneTab] = useState("script");
  const uploadButtonRef = useRef<HTMLButtonElement>(null);
  const workspaceHeadingRef = useRef<HTMLHeadingElement>(null);
  const { setProjectTitle, setScriptPosition } = useShell();

  const items = itemsQuery.data ?? [];
  const scenes = scriptQuery.data?.scenes ?? [];
  const selectedItem = items.find((item) => item.itemId === selectedItemId) ?? null;
  const detailQuery = useQuery({
    ...clearanceItemDetailQueryOptions({
      orgId: orgSlug,
      projectId,
      itemId: selectedItemId ?? "",
    }),
    enabled: selectedItemId !== null && isDrawerOpen,
  });

  const categoryCounts = items.reduce<Record<string, number>>((counts, item) => {
    const label = displayCategory(item.category);
    counts[label] = (counts[label] ?? 0) + 1;
    return counts;
  }, {});

  const filteredItems = items.filter((item) => {
    const matchesCategory =
      selectedCategory === "All" || displayCategory(item.category) === selectedCategory;
    const normalizedSearch = searchQuery.trim().toLowerCase();
    const matchesSearch =
      normalizedSearch.length === 0 ||
      item.entityName.toLowerCase().includes(normalizedSearch) ||
      item.category.toLowerCase().includes(normalizedSearch);
    return matchesCategory && matchesSearch;
  });

  /**
   * Every clearance item whose entity name appears on a script line. Multiple
   * flags may share one action line (e.g. Coca-Cola and Market Street).
   */
  const resolveLineFlags = useMemo(() => {
    const byName = new Map<string, ClearanceItem>();
    for (const item of items) {
      byName.set(item.entityName.toLowerCase(), item);
    }
    return (line: { type: string; text: string; flag?: string }): FlagAnnotation[] => {
      if (line.type === "scene_heading") return [];
      const lower = line.text.toLowerCase();
      const matched = new Map<string, ClearanceItem>();
      if (line.flag) {
        const explicit = byName.get(line.flag.toLowerCase());
        if (explicit) matched.set(explicit.itemId, explicit);
      }
      for (const item of items) {
        const term = item.entityName.toLowerCase();
        if (term.length < 3) continue;
        if (lower.includes(term)) matched.set(item.itemId, item);
      }
      return [...matched.values()]
        .map((item) => {
          const { severityClass, glyph } = severityOf(item);
          return {
            itemId: item.itemId,
            shortCategory: shortCategory(item.category),
            severityClass,
            glyph,
            status: displayStatus(item),
            term: item.entityName,
          } satisfies FlagAnnotation;
        })
        // Longest term first so buildSegments prefers the more specific span.
        .sort((a, b) => b.term.length - a.term.length);
    };
  }, [items]);

  /** Scenes that carry at least one flag, for the rail. */
  const scenesWithFlags = useMemo(
    () =>
      scenes
        .map((scene) => {
          const sceneItems = scene.lines
            .flatMap((line) => resolveLineFlags(line))
            .filter((annotation): annotation is FlagAnnotation => annotation !== null);
          const unique = new Map(sceneItems.map((annotation) => [annotation.itemId, annotation]));
          return { scene, flags: [...unique.values()] };
        })
        .filter((entry) => entry.flags.length > 0),
    [scenes, resolveLineFlags],
  );

  const errors = [scriptQuery.error, itemsQuery.error]
    .filter((error): error is Error => error instanceof Error)
    .map((error) => error.message);

  const openDrawer = (item: ClearanceItem) => {
    setSelectedItemId(item.itemId);
    setIsDrawerOpen(true);
  };

  const versionLabel = scriptQuery.data?.version ?? "v1";
  const versionNumber = Number(String(versionLabel).replace(/^v/i, "")) || 1;
  const stock = revisionStock(versionNumber);

  useEffect(() => {
    if (scriptQuery.data?.title) setProjectTitle(scriptQuery.data.title);
    return () => setProjectTitle(null);
  }, [scriptQuery.data?.title, setProjectTitle]);

  useEffect(() => {
    if (!selectedItem) {
      setScriptPosition(null);
      return;
    }
    const parts = [
      selectedItem.scene != null ? `Scene ${selectedItem.scene}` : null,
      (selectedItem as { page?: number }).page != null
        ? `p.${(selectedItem as { page?: number }).page}`
        : null,
    ].filter(Boolean);
    setScriptPosition(parts.length > 0 ? parts.join(" · ") : selectedItem.entityName);
    return () => setScriptPosition(null);
  }, [selectedItem, setScriptPosition]);

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
    <div className="page flush is-stage">
      <header className="page-head">
        <div className="page-head-row">
          <div>
            <h1 id="route-heading" ref={workspaceHeadingRef} tabIndex={-1}>
              Screenplay — {scriptQuery.data?.title ?? "Clearance Workspace"}
            </h1>
            <p className="page-lede">
              ClearCut presents sourced findings and unresolved risk for qualified human review. It
              does not provide legal advice or guarantee legal clearance.
            </p>
          </div>
          <div className="page-head-actions">
            <button
              ref={uploadButtonRef}
              className="button button-primary"
              type="button"
              onClick={() => setIsUploadOpen(true)}
            >
              Upload Script
            </button>
          </div>
        </div>
      </header>

      {errors.length > 0 && (
        <div className="page-notice">
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not load the workspace"
            message={errors.join(" ")}
            role="alert"
          />
        </div>
      )}

      <div className="mobile-pane-tabs">
        <TabsBar
          items={[
            { value: "script", label: "Script" },
            { value: "items", label: "Scenes" },
            { value: "evidence", label: "Evidence" },
          ]}
          active={paneTab}
          onChange={setPaneTab}
          label="Workspace view"
        />
      </div>

      <div
        className={`script-surface is-drawer-open ${
          paneTab === "items" ? "pane-rail" : paneTab === "evidence" ? "pane-evidence" : ""
        }`.trim()}
      >
        <aside className="scene-rail" aria-label="Scene navigator">
          <div className="scene-rail-head">
            <h2>Scenes &amp; flags</h2>
            <span className="mono muted">{items.length}</span>
          </div>
          {scenesWithFlags.map(({ scene, flags }) => (
            <div className="scene-group" key={scene.number}>
              <a className="scene-group-head" href={`#scene-${scene.number}`}>
                <span className="scene-number-inline mono">
                  {String(scene.number).padStart(2, "0")}
                </span>
                <span className="scene-slug-text">{scene.slug}</span>
                <span className="scene-count">{flags.length}</span>
              </a>
              {flags.map((annotation) => (
                <button
                  className="scene-flag"
                  type="button"
                  key={annotation.itemId}
                  aria-current={annotation.itemId === selectedItemId}
                  onClick={() => setSelectedItemId(annotation.itemId)}
                >
                  <span className={`flag-glyph ${annotation.severityClass}`} aria-hidden="true">
                    {annotation.glyph}
                  </span>
                  <span className="flag-term">{annotation.term}</span>
                  <Badge>{annotation.shortCategory}</Badge>
                </button>
              ))}
            </div>
          ))}
        </aside>

        <div className="script-scroll">
          <ScreenplayViewer
            title={scriptQuery.data?.title ?? "Screenplay"}
            version={`${versionLabel} (${stock} pages)`}
            scenes={scenes}
            loading={scriptQuery.isPending}
            selectedItemId={selectedItemId}
            stock={stock}
            resolveLineFlags={resolveLineFlags}
            onSelectFlag={(annotation) => setSelectedItemId(annotation.itemId)}
          />
        </div>

        <aside className="evidence-drawer" aria-label="Detected flags">
          <div className="drawer-head">
            <div className="min-w-0">
              <span className="slug-heading">Detected flags</span>
              <h2 className="gap-t-1">{filteredItems.length} shown</h2>
            </div>
          </div>
          <div className="drawer-body">
            <CategoryFilterBar
              selectedCategory={selectedCategory}
              onSelectCategory={setSelectedCategory}
              categoryCounts={categoryCounts}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              compact
            />

            {itemsQuery.isPending ? (
              <p role="status" className="small muted">
                Loading clearance items…
              </p>
            ) : filteredItems.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon" aria-hidden="true">
                  ◦
                </span>
                <h3>{items.length === 0 ? "No flags on this version" : "No matches"}</h3>
                <p>
                  {items.length === 0
                    ? "Flags appear here once the script has been checked."
                    : "No flags match the current filter."}
                </p>
              </div>
            ) : (
              <div className="list">
                {filteredItems.map((item) => (
                  <ClearanceItemCard
                    key={item.itemId}
                    item={item}
                    isSelected={selectedItemId === item.itemId}
                    onSelect={(selected) => setSelectedItemId(selected.itemId)}
                    onOpenDrawer={openDrawer}
                  />
                ))}
              </div>
            )}
          </div>
          {selectedItem && (
            <div className="drawer-foot">
              <div className="cluster-between">
                <span className="small truncate">{selectedItem.entityName}</span>
                <Badge tone={displayStatusTone(selectedItem)}>{displayStatus(selectedItem)}</Badge>
              </div>
            </div>
          )}
        </aside>
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
        nextVersionNumber={1}
        onSuccess={() => void refreshImportedScript()}
      />
    </div>
  );
}

export default WorkspaceRoute;

import React, { useState, useEffect } from "react";
import { Page, Badge } from "@clearcut/design-system";
import { loadProjectItems } from "../../../../../../lib/loaders.ts";

export function ItemWorklistRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string };
}) {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    loadProjectItems(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01"
    ).then(setItems);
  }, [params?.orgSlug, params?.projectId]);

  return (
    <Page
      title="Clearance Item Worklist"
      subtitle="Filterable list and board of all candidate clearance items across 10 categories"
      trail={[{ label: "Overview", href: ".." }, { label: "Items" }]}
    >
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-4">
        <div className="flex items-center space-x-3 mb-4">
          <input
            type="text"
            placeholder="Search items..."
            className="p-2 border border-slate-300 dark:border-slate-700 rounded text-xs w-64 bg-transparent"
          />
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
          <div className="py-3 flex items-center justify-between">
            <div>
              <span className="font-semibold text-slate-900 dark:text-white">Coca-Cola</span>
              <span className="ml-2 text-slate-400">Products & Trademarks (Scene 1)</span>
            </div>
            <Badge label="Needs Review" variant="warning" />
          </div>
        </div>
      </div>
    </Page>
  );
}

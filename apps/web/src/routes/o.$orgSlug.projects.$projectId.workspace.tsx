import React from "react";
import { Page } from "@clearcut/design-system";

export function ScreenplayWorkspaceRoute() {
  return (
    <Page
      title="Screenplay Clearance Workspace"
      subtitle="Annotated screenplay viewer with inline margin flags and evidence drawer"
      trail={[
        { label: "Overview", href: "." },
        { label: "Script Workspace" },
      ]}
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-6 font-mono text-sm">
          <div className="text-slate-400 text-xs mb-4">SCENE 1 - EXT. CAFE - DAY</div>
          <p className="leading-relaxed">
            JOHN sips a can of <span className="bg-amber-100 dark:bg-amber-900/60 px-1 border-b-2 border-amber-500 font-semibold cursor-pointer">Coca-Cola</span> while reading a novel by <span className="bg-amber-100 dark:bg-amber-900/60 px-1 border-b-2 border-amber-500 font-semibold cursor-pointer">Stephen King</span>.
          </p>
        </div>
        <div className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">Evidence Drawer</h3>
          <p className="text-xs text-slate-500">Select any highlighted span to inspect Parallel Search provenance.</p>
        </div>
      </div>
    </Page>
  );
}

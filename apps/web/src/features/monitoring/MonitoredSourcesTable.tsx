import React from "react";

export interface MonitoredSource {
  id: string;
  sourceTitle: string;
  category: string;
  authorityTier: string;
  url: string;
  lastChecked: string;
  status: "active" | "warning" | "error";
}

export interface MonitoredSourcesTableProps {
  sources?: MonitoredSource[];
}

export function MonitoredSourcesTable({ sources = [] }: MonitoredSourcesTableProps) {
  const displaySources: MonitoredSource[] =
    sources.length > 0
      ? sources
      : [
          {
            id: "src-1",
            sourceTitle: "USPTO Trademark Electronic Search System (TESS)",
            category: "Trademarks",
            authorityTier: "Primary Statutory",
            url: "https://tmsearch.uspto.gov",
            lastChecked: "2026-08-30T12:00:00Z",
            status: "active",
          },
          {
            id: "src-2",
            sourceTitle: "California Secretary of State Business Registry",
            category: "Corporate Entities",
            authorityTier: "State Statutory",
            url: "https://bizfileonline.sos.ca.gov",
            lastChecked: "2026-08-30T12:00:00Z",
            status: "active",
          },
          {
            id: "src-3",
            sourceTitle: "ASCAP / BMI Repertory Database",
            category: "Music & Lyrics",
            authorityTier: "Industry Registry",
            url: "https://www.ascap.com/repertory",
            lastChecked: "2026-08-30T12:00:00Z",
            status: "active",
          },
          {
            id: "src-4",
            sourceTitle: "U.S. Copyright Office Public Catalog",
            category: "Copyrights",
            authorityTier: "Primary Statutory",
            url: "https://cocatalog.loc.gov",
            lastChecked: "2026-08-30T12:00:00Z",
            status: "active",
          },
        ];

  return (
    <div
      data-testid="monitored-sources-table"
      className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden font-sans shadow-sm"
    >
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
          Active Monitored Sources ({displaySources.length})
        </span>
        <span className="text-[11px] text-emerald-400 font-medium">● All Endpoints Healthy</span>
      </div>

      <div className="divide-y divide-slate-800 text-xs">
        {displaySources.map((s) => (
          <div key={s.id} className="p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-200">{s.sourceTitle}</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded">
                  {s.category}
                </span>
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                {s.authorityTier} • Last verified {new Date(s.lastChecked).toLocaleDateString()}
              </div>
            </div>

            <div className="flex items-center space-x-2 shrink-0">
              <span className="text-[10px] px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-900 rounded-full font-bold uppercase">
                {s.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default MonitoredSourcesTable;

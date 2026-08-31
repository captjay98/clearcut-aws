import React from "react";

export interface LineageEvent {
  versionOrdinal: number;
  date: string;
  eventType: string;
  description: string;
  actor: string;
}

export interface ItemLineageDrawerProps {
  events?: LineageEvent[];
}

export function ItemLineageDrawer({ events = [] }: ItemLineageDrawerProps) {
  const displayEvents: LineageEvent[] =
    events.length > 0
      ? events
      : [
          {
            versionOrdinal: 2,
            date: "2026-08-30T16:00:00Z",
            eventType: "Rewrite Accepted",
            description: "Changed 'Vega Camera' to fictional 'Aero Optics Mark IV'. Item status updated to cleared.",
            actor: "Jamie Park (Reviewer)",
          },
          {
            versionOrdinal: 1,
            date: "2026-08-30T12:00:00Z",
            eventType: "Detection & Decision",
            description: "Detected 'Vega Camera' in Scene 1. Flagged as Needs Call due to active USPTO trademark.",
            actor: "ClearCut Engine & Sarah Chen",
          },
          {
            versionOrdinal: 1,
            date: "2026-08-30T10:00:00Z",
            eventType: "Initial Import",
            description: "Screenplay manuscript v1 imported and parsed.",
            actor: "Jamie Park (Writer)",
          },
        ];

  return (
    <div
      data-testid="item-lineage-section"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-white">Item Lineage & Audit Trail</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Chronological revision history across script versions.
          </p>
        </div>
        <span className="text-xs px-2.5 py-0.5 bg-slate-800 text-slate-300 rounded font-mono">
          Audit Verified
        </span>
      </div>

      <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
        {displayEvents.map((evt, idx) => (
          <div key={idx} className="relative space-y-1 text-xs">
            {/* Timeline node */}
            <div className="absolute -left-6 top-1 w-2.5 h-2.5 rounded-full bg-amber-500 ring-4 ring-slate-900" />

            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">
                Version {evt.versionOrdinal}: {evt.eventType}
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                {new Date(evt.date).toLocaleDateString()}
              </span>
            </div>

            <p className="text-slate-300">{evt.description}</p>
            <div className="text-[10px] text-slate-500">By {evt.actor}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ItemLineageDrawer;

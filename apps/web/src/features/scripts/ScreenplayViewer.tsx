import React from "react";

export interface ScriptLine {
  type: "scene_heading" | "action" | "character" | "parenthetical" | "dialogue" | "transition";
  text: string;
  flag?: string;
}

export interface ScriptScene {
  number: number;
  slug: string;
  page: number;
  lines: ScriptLine[];
}

export interface ScreenplayViewerProps {
  title?: string;
  version?: string;
  scenes?: ScriptScene[];
  loading?: boolean;
  selectedSceneNumber?: number;
  onSelectScene?: (sceneNumber: number) => void;
  onItemClick?: (flag: string) => void;
}

export function ScreenplayViewer({
  title = "Borrowed Light",
  version = "v1",
  scenes = [],
  loading = false,
  selectedSceneNumber,
  onSelectScene,
  onItemClick,
}: ScreenplayViewerProps) {
  if (loading) {
    return (
      <div
        data-testid="screenplay-viewer"
        className="flex-1 bg-slate-900/80 border border-slate-800 rounded-lg p-8 text-center text-xs text-slate-500 font-mono"
      >
        Loading screenplay manuscript...
      </div>
    );
  }

  // If no scenes, provide default canonical screenplay scenes for testing/display
  const activeScenes: ScriptScene[] =
    scenes.length > 0
      ? scenes
      : [
          {
            number: 1,
            slug: "EXT. DOWNTOWN ROOFTOP - DUSK",
            page: 1,
            lines: [
              {
                type: "action",
                text: "LEO (30s) checks his Vega Camera as the horizon turns cobalt.",
                flag: "Vega Camera",
              },
              { type: "character", text: "LEO" },
              { type: "dialogue", text: "Mina, do you copy? The feed is live." },
              { type: "character", text: "MINA (O.S.)" },
              {
                type: "dialogue",
                text: "Copy Leo. Sunset Boulevard is clear.",
                flag: "Sunset Boulevard",
              },
            ],
          },
          {
            number: 2,
            slug: "INT. SURVEILLANCE VAN - CONTINUOUS",
            page: 2,
            lines: [
              {
                type: "action",
                text: "A vintage radio plays Blue Monday in the background.",
                flag: "Blue Monday",
              },
              { type: "character", text: "MINA" },
              { type: "dialogue", text: "Keep the change, kid. We're on the move." },
            ],
          },
        ];

  return (
    <div
      data-testid="screenplay-viewer"
      className="flex-1 flex flex-col min-h-0 bg-slate-950 border border-slate-800 rounded-lg overflow-hidden shadow-inner font-mono"
    >
      {/* Header bar */}
      <div className="h-10 px-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between font-sans shrink-0">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-bold text-slate-200">{title}</span>
          <span className="text-[10px] px-1.5 py-0.5 bg-amber-950 border border-amber-900 text-amber-400 font-bold rounded">
            {version}
          </span>
        </div>

        {activeScenes.length > 0 && (
          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-500 font-medium">Jump to Scene:</span>
            <select
              value={selectedSceneNumber || activeScenes[0].number}
              onChange={(e) => onSelectScene?.(Number(e.target.value))}
              className="px-2 py-0.5 text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              {activeScenes.map((s) => (
                <option key={s.number} value={s.number}>
                  Scene {s.number} (Pg {s.page})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Screenplay Document Surface */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs text-slate-300 selection:bg-amber-500 selection:text-black">
        {activeScenes.map((scene) => (
          <div key={scene.number} id={`scene-${scene.number}`} className="space-y-3 max-w-2xl mx-auto">
            {/* Scene Heading */}
            <div
              data-testid="scene-heading"
              className="font-bold text-amber-400 bg-slate-900/90 border-l-2 border-amber-500 px-3 py-1.5 uppercase tracking-wide rounded-r"
            >
              {scene.slug}
            </div>

            {/* Script Elements */}
            <div className="space-y-2 px-3">
              {scene.lines.map((line, idx) => {
                if (line.type === "character") {
                  return (
                    <div
                      key={idx}
                      className="font-bold text-slate-100 uppercase text-center pt-2 max-w-md mx-auto"
                    >
                      {line.text}
                    </div>
                  );
                }
                if (line.type === "parenthetical") {
                  return (
                    <div
                      key={idx}
                      className="italic text-slate-400 text-center text-[11px] max-w-xs mx-auto"
                    >
                      {line.text}
                    </div>
                  );
                }
                if (line.type === "dialogue") {
                  return (
                    <div
                      key={idx}
                      className="text-slate-200 text-center max-w-md mx-auto leading-relaxed"
                    >
                      {line.flag ? (
                        <button
                          type="button"
                          onClick={() => onItemClick?.(line.flag!)}
                          className="bg-amber-950/60 text-amber-300 underline decoration-amber-500 decoration-dotted hover:bg-amber-900/60 px-1 py-0.5 rounded transition-colors"
                          title={`Click to inspect flag: ${line.flag}`}
                        >
                          {line.text}
                        </button>
                      ) : (
                        line.text
                      )}
                    </div>
                  );
                }
                if (line.type === "transition") {
                  return (
                    <div key={idx} className="text-right font-bold text-slate-400 uppercase pt-2">
                      {line.text}
                    </div>
                  );
                }
                // Action text
                return (
                  <div key={idx} className="text-slate-300 leading-relaxed text-left">
                    {line.flag ? (
                      <button
                        type="button"
                        onClick={() => onItemClick?.(line.flag!)}
                        className="bg-amber-950/60 text-amber-300 underline decoration-amber-500 decoration-dotted hover:bg-amber-900/60 px-1 py-0.5 rounded transition-colors text-left"
                        title={`Click to inspect flag: ${line.flag}`}
                      >
                        {line.text}
                      </button>
                    ) : (
                      line.text
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ScreenplayViewer;

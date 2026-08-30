import React, { useState } from "react";

interface ImportStepProps {
  onFileSelected: (file: File) => void;
  onPasteSubmitted: (text: string) => void;
}

export function ImportStep({ onFileSelected, onPasteSubmitted }: ImportStepProps) {
  const [tab, setTab] = useState<"upload" | "paste">("upload");
  const [pasteText, setPasteText] = useState("");

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelected(e.dataTransfer.files[0]);
    }
  };

  return (
    <div>
      <div className="flex border-b border-slate-200 dark:border-slate-800 mb-6">
        <button
          type="button"
          onClick={() => setTab("upload")}
          className={`pb-2 px-4 text-sm font-medium border-b-2 ${
            tab === "upload"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          Upload Screenplay File
        </button>
        <button
          type="button"
          onClick={() => setTab("paste")}
          className={`pb-2 px-4 text-sm font-medium border-b-2 ${
            tab === "paste"
              ? "border-blue-600 text-blue-600 dark:text-blue-400"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          Paste Screenplay Text
        </button>
      </div>

      {tab === "upload" ? (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          className="border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-lg p-10 text-center hover:border-blue-500 transition-colors"
        >
          <p className="text-slate-600 dark:text-slate-300 font-medium mb-1">
            Drag and drop your screenplay here
          </p>
          <p className="text-xs text-slate-400 mb-4">Supported formats: Fountain (.fountain), FinalDraft (.fdx), PDF (.pdf), Plain Text (.txt)</p>
          <label className="cursor-pointer inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700">
            Browse File
            <input
              type="file"
              accept=".fountain,.fdx,.pdf,.txt"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  onFileSelected(e.target.files[0]);
                }
              }}
            />
          </label>
        </div>
      ) : (
        <div className="space-y-4">
          <textarea
            rows={10}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="INT. COFFEE SHOP - DAY..."
            className="w-full p-3 font-mono text-sm border border-slate-300 dark:border-slate-700 rounded-md bg-transparent text-slate-900 dark:text-white"
          />
          <button
            type="button"
            disabled={!pasteText.trim()}
            onClick={() => onPasteSubmitted(pasteText)}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            Parse Pasted Text
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useEffect, useRef, useState } from "react";
import { api, type ParseRun, type ScriptVersion } from "@clearcut/contracts";

export interface ScriptUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  orgSlug: string;
  projectId: string;
  returnFocusRef: React.RefObject<HTMLElement>;
  successFocusRef: React.RefObject<HTMLElement>;
  onSuccess: (version: ScriptVersion) => void | Promise<void>;
}

type ImportMode = "file" | "paste";
type ImportStep = "select" | "diagnostics";

function contentTypeForFile(file: File): string {
  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith(".fdx")) return "application/xml";
  return "text/plain";
}

export function ScriptUploadModal({
  isOpen,
  onClose,
  orgSlug,
  projectId,
  returnFocusRef,
  successFocusRef,
  onSuccess,
}: ScriptUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [pastedText, setPastedText] = useState("");
  const [mode, setMode] = useState<ImportMode>("file");
  const [step, setStep] = useState<ImportStep>("select");
  const [parseRun, setParseRun] = useState<ParseRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const commitSucceededRef = useRef(false);
  const loadingRef = useRef(false);

  const reset = () => {
    setFile(null);
    setPastedText("");
    setMode("file");
    setStep("select");
    setParseRun(null);
    setError(null);
  };

  const close = () => {
    if (loading) return;
    reset();
    onClose();
  };

  useEffect(() => {
    loadingRef.current = loading;
    if (loading) {
      dialogRef.current?.focus();
    }
  }, [loading]);

  useEffect(() => {
    if (!isOpen) return;
    commitSucceededRef.current = false;
    previousFocusRef.current =
      returnFocusRef.current ?? (document.activeElement as HTMLElement | null);
    const focusTimer = window.requestAnimationFrame(() => {
      dialogRef.current
        ?.querySelector<HTMLElement>("button, input, textarea, select, [tabindex]:not([tabindex='-1'])")
        ?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !loadingRef.current) {
        event.preventDefault();
        reset();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input:not(:disabled), textarea:not(:disabled), " +
            "select:not(:disabled), [tabindex]:not([tabindex='-1'])",
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeElement = document.activeElement;
      if (
        activeElement === dialogRef.current ||
        !activeElement ||
        !dialogRef.current.contains(activeElement)
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      const previousFocus = previousFocusRef.current;
      const nextFocus = commitSucceededRef.current
        ? successFocusRef.current
        : previousFocus;
      previousFocusRef.current = null;
      commitSucceededRef.current = false;
      window.requestAnimationFrame(() => {
        if (nextFocus?.isConnected) nextFocus.focus();
      });
    };
  }, [isOpen, onClose, returnFocusRef, successFocusRef]);

  if (!isOpen) return null;

  const handleFileDrop = (event: React.DragEvent) => {
    event.preventDefault();
    const droppedFile = event.dataTransfer.files?.[0];
    if (droppedFile) setFile(droppedFile);
  };

  const handleAnalyze = async () => {
    setError(null);
    setLoading(true);

    try {
      let artifactId: string;
      if (mode === "file" && file) {
        const contentType = contentTypeForFile(file);
        const capability = await api.createUploadCapability({
          params: { orgId: orgSlug, projectId },
          body: { filename: file.name, contentType },
        });
        if (!capability.ok) {
          setError(capability.error.message);
          return;
        }

        const typedFile = new File([file], file.name, { type: contentType });
        const finalized = await api.finalizeImportArtifact({
          params: {
            orgId: orgSlug,
            projectId,
            artifactId: capability.value.capabilityId,
          },
          body: { file: typedFile },
          headers: { "X-Upload-Nonce": capability.value.nonce },
        });
        if (!finalized.ok) {
          setError(finalized.error.message);
          return;
        }
        artifactId = finalized.value.artifactId;
      } else if (mode === "paste" && pastedText.trim()) {
        const created = await api.createPasteImport({
          params: { orgId: orgSlug, projectId },
          body: { rawText: pastedText, format: "fountain" },
        });
        if (!created.ok) {
          setError(created.error.message);
          return;
        }
        artifactId = created.value.artifactId;
      } else {
        setError("Choose a screenplay file or paste screenplay text.");
        return;
      }

      const parsed = await api.parseImportArtifact({
        params: { orgId: orgSlug, projectId, artifactId },
      });
      if (!parsed.ok) {
        setError(parsed.error.message);
        return;
      }
      setParseRun(parsed.value);
      setStep("diagnostics");
    } catch {
      setError("The screenplay import request could not be completed.");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!parseRun) return;
    setError(null);
    setLoading(true);

    try {
      let acceptedRun = parseRun;
      if (parseRun.warnings.length > 0 && !parseRun.warningsAccepted) {
        const accepted = await api.acceptParseWarnings({
          params: { orgId: orgSlug, projectId, runId: parseRun.runId },
        });
        if (!accepted.ok) {
          setError(accepted.error.message);
          return;
        }
        acceptedRun = accepted.value;
        setParseRun(accepted.value);
      }

      const committed = await api.commitScriptVersion({
        params: { orgId: orgSlug, projectId, runId: acceptedRun.runId },
      });
      if (!committed.ok) {
        setError(committed.error.message);
        return;
      }

      try {
        await onSuccess(committed.value);
        commitSucceededRef.current = true;
        reset();
        onClose();
      } catch {
        setParseRun(null);
        setError(
          "Version one was committed, but this view could not resume it. Close and reload to continue from the persisted version.",
        );
      }
    } catch {
      setError("Version one could not be committed.");
    } finally {
      setLoading(false);
    }
  };

  const dialogTitle =
    step === "select" ? "Import Screenplay" : "Parser Diagnostics & Verification";

  return (
    <div
      data-testid="script-upload-modal"
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="script-import-title"
        tabIndex={-1}
        className="card w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden flex flex-col"
      >
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 id="script-import-title" className="text-base font-bold text-white">
            {dialogTitle}
          </h2>
          <button
            type="button"
            onClick={close}
            disabled={loading}
            aria-label="Close import dialog"
            className="text-slate-400 hover:text-white disabled:opacity-50 text-lg font-bold"
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-4 text-xs">
          {error && (
            <div role="alert" className="p-3 bg-red-950/50 border border-red-900 rounded text-red-400">
              {error}
            </div>
          )}

          {step === "select" ? (
            <>
              <div className="flex space-x-2 border-b border-slate-800 pb-2">
                <button
                  type="button"
                  onClick={() => setMode("file")}
                  aria-pressed={mode === "file"}
                  className={`px-3 py-1 font-bold rounded ${
                    mode === "file"
                      ? "bg-amber-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  File Upload (.Fountain, .FDX, .TXT)
                </button>
                <button
                  type="button"
                  onClick={() => setMode("paste")}
                  aria-pressed={mode === "paste"}
                  className={`px-3 py-1 font-bold rounded ${
                    mode === "paste"
                      ? "bg-amber-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Paste Screenplay Text
                </button>
              </div>

              {mode === "file" ? (
                <div
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleFileDrop}
                  className="p-8 border-2 border-dashed border-slate-700 hover:border-amber-500/60 rounded-lg text-center bg-slate-800/30 transition-colors"
                >
                  <div className="text-3xl mb-2" aria-hidden="true">📄</div>
                  <p className="text-slate-300 font-medium mb-1">
                    Drag and drop a Fountain, Final Draft, or text screenplay
                  </p>
                  <p className="text-[11px] text-slate-500 mb-4">Up to 25MB supported</p>
                  <label className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-amber-400 font-bold rounded cursor-pointer border border-slate-700">
                    Browse Files
                    <input
                      type="file"
                      aria-label="Screenplay file"
                      accept=".fountain,.fdx,.txt"
                      className="sr-only"
                      onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  {file && (
                    <div className="mt-3 text-emerald-400 font-medium">Selected: {file.name}</div>
                  )}
                </div>
              ) : (
                <div>
                  <label htmlFor="pasted-script" className="block text-slate-300 font-medium mb-1">
                    Screenplay Text Content
                  </label>
                  <textarea
                    id="pasted-script"
                    rows={8}
                    value={pastedText}
                    onChange={(event) => setPastedText(event.target.value)}
                    placeholder="EXT. DOWNTOWN ROOFTOP - DUSK"
                    className="w-full p-3 font-mono text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
              )}
            </>
          ) : parseRun ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2 text-center">
                <div className="p-3 bg-slate-800/60 rounded border border-slate-700">
                  <div className="text-slate-400 text-[10px]">Scenes</div>
                  <div className="text-base font-bold text-amber-400">{parseRun.sceneCount}</div>
                </div>
                <div className="p-3 bg-slate-800/60 rounded border border-slate-700">
                  <div className="text-slate-400 text-[10px]">Elements</div>
                  <div className="text-base font-bold text-amber-400">{parseRun.elementCount}</div>
                </div>
              </div>

              {parseRun.warnings.length > 0 ? (
                <div className="p-3 bg-amber-950/30 border border-amber-800/60 rounded-lg space-y-1.5">
                  <div className="font-bold text-amber-300">
                    Parser warnings requiring acceptance ({parseRun.warnings.length})
                  </div>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    {parseRun.warnings.map((warning, index) => (
                      <li key={`${warning.code}-${warning.line ?? index}`}>
                        {warning.line ? `Line ${warning.line}: ` : ""}
                        {warning.message}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="p-3 bg-emerald-950/30 border border-emerald-800/60 rounded text-emerald-300">
                  Parse completed without warnings.
                </div>
              )}
            </div>
          ) : null}
        </div>

        <div className="px-5 py-3 border-t border-slate-800 flex items-center justify-end space-x-3 bg-slate-900/60">
          <button
            type="button"
            onClick={close}
            disabled={loading}
            className="px-4 py-2 text-slate-400 hover:text-white disabled:opacity-50 font-medium text-xs"
          >
            Cancel
          </button>
          {step === "select" ? (
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={loading || (mode === "file" ? !file : !pastedText.trim())}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow"
            >
              {loading ? "Uploading & Parsing..." : "Upload & Analyze"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCommit}
              disabled={loading || !parseRun}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow"
            >
              {loading
                ? "Committing Version 1..."
                : parseRun && parseRun.warnings.length > 0 && !parseRun.warningsAccepted
                  ? "Accept Warnings & Commit Version 1"
                  : "Commit Version 1"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ScriptUploadModal;

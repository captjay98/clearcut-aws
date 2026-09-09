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
  /**
   * "initial" imports the project's first version; "revision" imports a
   * follow-up revision to compare and selectively rescan against. Copy is
   * derived from this — no version number is ever hard-coded.
   */
  purpose?: "initial" | "revision";
  /**
   * The version this commit will create, so the confirming button names it.
   * Derived from the project's persisted versions by the caller rather than
   * assumed here, and defaulted to the first version.
   */
  nextVersionNumber?: number;
}

type ImportMode = "file" | "paste";
type ImportStep = "select" | "diagnostics";

interface PurposeCopy {
  dialogTitle: string;
  commitIdle: string;
  commitAccept: string;
  commitBusy: string;
  commitFailure: string;
  resumeFailure: string;
}

function copyForPurpose(purpose: "initial" | "revision", nextVersionNumber: number): PurposeCopy {
  if (purpose === "revision") {
    return {
      dialogTitle: "Import Revision",
      commitIdle: `Commit Revision ${nextVersionNumber}`,
      commitAccept: `Accept Warnings & Commit Revision ${nextVersionNumber}`,
      commitBusy: "Committing Revision…",
      commitFailure: "The revision could not be committed.",
      resumeFailure:
        "The revision was committed, but this view could not resume it. Close and reload to continue from the persisted version.",
    };
  }
  return {
    dialogTitle: "Import Screenplay",
    commitIdle: `Commit Version ${nextVersionNumber}`,
    commitAccept: `Accept Warnings & Commit Version ${nextVersionNumber}`,
    commitBusy: "Committing Version…",
    commitFailure: "The screenplay version could not be committed.",
    resumeFailure:
      "The version was committed, but this view could not resume it. Close and reload to continue from the persisted version.",
  };
}

function contentTypeForFile(file: File): string {
  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith(".fdx")) return "application/xml";
  if (lowerName.endsWith(".pdf")) return "application/pdf";
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
  purpose = "initial",
  nextVersionNumber = 1,
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
  const copy = copyForPurpose(purpose, nextVersionNumber);

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
        setError(copy.resumeFailure);
      }
    } catch {
      setError(copy.commitFailure);
    } finally {
      setLoading(false);
    }
  };

  const dialogTitle =
    step === "select" ? copy.dialogTitle : "Parser Diagnostics & Verification";

  return (
    <div data-testid="script-upload-modal" className="backdrop">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="script-import-title"
        tabIndex={-1}
        className="dialog"
      >
        <header className="dialog-head">
          <div>
            <h2 id="script-import-title">{dialogTitle}</h2>
          </div>
          <button
            className="icon-button is-bare"
            type="button"
            onClick={close}
            disabled={loading}
            aria-label="Close import dialog"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>

        <div className="dialog-body">
          <div className="stack">
            {error && (
              <div className="banner is-danger" role="alert">
                <span className="banner-icon" aria-hidden="true">
                  ⚠
                </span>
                <div className="banner-body">
                  <p>{error}</p>
                </div>
              </div>
            )}

            {step === "select" ? (
              <>
                <div className="tabs" role="group" aria-label="Choose how to bring in the script">
                  <button
                    className="tab"
                    type="button"
                    onClick={() => setMode("file")}
                    aria-pressed={mode === "file"}
                  >
                    File Upload (.Fountain, .FDX, .PDF, .TXT)
                  </button>
                  <button
                    className="tab"
                    type="button"
                    onClick={() => setMode("paste")}
                    aria-pressed={mode === "paste"}
                  >
                    Paste Screenplay Text
                  </button>
                </div>

                {mode === "file" ? (
                  <div
                    className="empty-state"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={handleFileDrop}
                  >
                    <span className="empty-icon" aria-hidden="true">
                      ⌑
                    </span>
                    <h3>Drag and drop a Fountain, Final Draft, PDF, or text screenplay</h3>
                    <p>
                      Up to 25MB. A PDF must carry extractable text; scanned pages are
                      reported, never guessed at.
                    </p>
                    <label className="button button-secondary">
                      Browse Files
                      <input
                        type="file"
                        aria-label="Screenplay file"
                        accept=".fountain,.fdx,.pdf,.txt"
                        className="sr-only"
                        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                      />
                    </label>
                    {file && (
                      <p className="small">
                        Selected: <strong>{file.name}</strong>
                      </p>
                    )}
                  </div>
                ) : (
                  <label className="field" htmlFor="pasted-script">
                    <span className="field-label">Screenplay Text Content</span>
                    <textarea
                      id="pasted-script"
                      className="mono"
                      rows={8}
                      value={pastedText}
                      onChange={(event) => setPastedText(event.target.value)}
                      placeholder="EXT. DOWNTOWN ROOFTOP - DUSK"
                    />
                  </label>
                )}
              </>
            ) : parseRun ? (
              <>
                <div className="grid grid-2">
                  <div className="stat">
                    <span className="stat-label">Scenes</span>
                    <span className="stat-value">{parseRun.sceneCount}</span>
                  </div>
                  <div className="stat">
                    <span className="stat-label">Elements</span>
                    <span className="stat-value">{parseRun.elementCount}</span>
                  </div>
                </div>

                {parseRun.warnings.length > 0 ? (
                  <div className="banner is-warning">
                    <span className="banner-icon" aria-hidden="true">
                      ⚠
                    </span>
                    <div className="banner-body">
                      <strong>
                        Parser warnings requiring acceptance ({parseRun.warnings.length})
                      </strong>
                      <ul className="small">
                        {parseRun.warnings.map((warning, index) => (
                          <li key={`${warning.code}-${warning.line ?? index}`}>
                            {warning.line ? `Line ${warning.line}: ` : ""}
                            {warning.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ) : (
                  <div className="banner is-success">
                    <span className="banner-icon" aria-hidden="true">
                      ✓
                    </span>
                    <div className="banner-body">
                      <p>Parse completed without warnings.</p>
                    </div>
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>

        <footer className="dialog-actions">
          <button className="button button-quiet" type="button" onClick={close} disabled={loading}>
            Cancel
          </button>
          {step === "select" ? (
            <button
              className="button button-primary"
              type="button"
              onClick={handleAnalyze}
              disabled={loading || (mode === "file" ? !file : !pastedText.trim())}
            >
              {loading ? "Uploading & Parsing..." : "Upload & Analyze"}
            </button>
          ) : (
            <button
              className="button button-primary"
              type="button"
              onClick={handleCommit}
              disabled={loading || !parseRun}
            >
              {loading
                ? copy.commitBusy
                : parseRun && parseRun.warnings.length > 0 && !parseRun.warningsAccepted
                  ? copy.commitAccept
                  : copy.commitIdle}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

export default ScriptUploadModal;

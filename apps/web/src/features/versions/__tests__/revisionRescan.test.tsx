// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Job,
  ScriptDiffElement,
  ScriptDiffSummary,
  ScriptVersionDiff,
} from "@clearcut/contracts";

import { VersionDiffViewer } from "../VersionDiffViewer";
import { RescanProgress } from "../RescanProgress";
import { SelectiveRescanDialog } from "../SelectiveRescanDialog";
import { ScriptUploadModal } from "../../scripts/ScriptUploadModal";
import {
  jobQueryOptions,
  scriptVersionKeys,
  isTerminalRunStatus,
} from "../../../queries/scriptVersions";
import { startSelectiveRescanMutationOptions } from "../../../mutations/scriptVersionCommands";

afterEach(cleanup);

// ── Shared fixtures ───────────────────────────────────────────────────────
const SCOPE = { orgSlug: "org-slug", projectId: "project-1" };

function makeSummary(over: Partial<ScriptDiffSummary> = {}): ScriptDiffSummary {
  return {
    unchanged: 3,
    moved: 1,
    modified: 2,
    added: 1,
    removed: 1,
    affectedElementCount: 4,
    carriedForwardItemCount: 5,
    carriedForwardEvidenceCount: 9,
    providerWorkEstimate: 12,
    ...over,
  };
}

const DIFF_ELEMENTS: ScriptDiffElement[] = [
  { afterElementId: "e-u", beforeElementId: "e-u", type: "action", text: "EXT. ROOFTOP - DAY", changeKind: "unchanged", confidence: "exact" },
  { afterElementId: "e-m", beforeElementId: "e-m", type: "action", text: "A CAN OF SPARKLING COLA", changeKind: "modified", confidence: "contextual" },
  { afterElementId: "e-a", type: "action", text: "She lifts a vintage Vega camera.", changeKind: "added", confidence: "unmatched" },
  { beforeElementId: "e-r", type: "action", text: "The neon sign flickers.", changeKind: "removed", confidence: "unmatched" },
  { afterElementId: "e-mv", beforeElementId: "e-mv", type: "scene_heading", text: "INT. STUDIO - NIGHT", changeKind: "moved", confidence: "similar" },
];

function makeJob(over: Partial<Job> = {}): Job {
  return {
    jobId: "job-1",
    status: "running",
    jobType: "selective_rescan",
    target: { type: "script_version", id: "v-2" },
    canRetry: false,
    progress: 40,
    stage: "researching_affected_items",
    resultSummary: null,
    error: null,
    attemptCount: 1,
    attempts: [],
    history: [],
    availableAt: "2026-09-06T00:00:00Z",
    createdAt: "2026-09-06T00:00:00Z",
    updatedAt: "2026-09-06T00:00:10Z",
    ...over,
  };
}

// ── VersionDiffViewer ─────────────────────────────────────────────────────
describe("VersionDiffViewer renders authoritative generated diff data", () => {
  it("has no built-in fake rows and shows an empty state for an empty diff", () => {
    render(
      <VersionDiffViewer
        beforeLabel="v1 (White)"
        afterLabel="v2 (Blue)"
        elements={[]}
      />,
    );
    const viewer = screen.getByTestId("script-diff-viewer");
    expect(viewer.textContent).not.toContain("COCA-COLA");
    expect(viewer.textContent).not.toContain("Vega Camera");
    expect(screen.getByText(/no element-level changes/i)).toBeTruthy();
  });

  it("renders all five diff kinds from generated elements", () => {
    render(
      <VersionDiffViewer
        beforeLabel="v1"
        afterLabel="v2"
        elements={DIFF_ELEMENTS}
      />,
    );
    const viewer = screen.getByTestId("script-diff-viewer");
    expect(within(viewer).getAllByTestId("diff-row")).toHaveLength(5);
    expect(viewer.querySelector('[data-change-kind="unchanged"]')).toBeTruthy();
    expect(viewer.querySelector('[data-change-kind="modified"]')).toBeTruthy();
    expect(viewer.querySelector('[data-change-kind="added"]')).toBeTruthy();
    expect(viewer.querySelector('[data-change-kind="removed"]')).toBeTruthy();
    expect(viewer.querySelector('[data-change-kind="moved"]')).toBeTruthy();
  });

  it("filters rows by change kind", async () => {
    const user = userEvent.setup();
    render(<VersionDiffViewer beforeLabel="v1" afterLabel="v2" elements={DIFF_ELEMENTS} />);
    await user.click(screen.getByRole("button", { name: /added/i }));
    const viewer = screen.getByTestId("script-diff-viewer");
    const rows = within(viewer).getAllByTestId("diff-row");
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute("data-change-kind")).toBe("added");
  });
});

// ── RescanProgress ────────────────────────────────────────────────────────
describe("RescanProgress reconstructs from a persisted job", () => {
  it("renders persisted progress, stage and counts with an aria-live region", () => {
    render(
      <RescanProgress
        job={makeJob({ status: "running", progress: 40, stage: "researching_affected_items" })}
        summary={makeSummary()}
      />,
    );
    const region = screen.getByTestId("rescan-progress");
    expect(region.getAttribute("aria-live")).toBeTruthy();
    expect(region.textContent).toContain("researching_affected_items");
    // affected & carried counts sourced from the diff summary, not timers
    expect(region.textContent).toContain("4");
    expect(region.textContent).toContain("5");
  });

  it("shows a terminal success result group when the job succeeded", () => {
    render(
      <RescanProgress
        job={makeJob({ status: "succeeded", progress: 100, resultSummary: { rescanned: 4, carried: 5 } })}
        summary={makeSummary()}
      />,
    );
    expect(screen.getByTestId("rescan-result-success")).toBeTruthy();
    expect(screen.getByTestId("rescan-result-success").textContent).toMatch(
      /completed|rescanned/i,
    );
  });

  it("shows the typed redacted error and retry eligibility on failure", () => {
    render(
      <RescanProgress
        job={makeJob({
          status: "failed",
          canRetry: true,
          error: { code: "research_provider_unavailable", message: "Provider temporarily unavailable.", retryable: true },
        })}
        summary={makeSummary()}
      />,
    );
    const region = screen.getByTestId("rescan-progress");
    expect(region.textContent).toContain("Provider temporarily unavailable.");
    expect(region.textContent).toContain("research_provider_unavailable");
    expect(screen.getByText(/can be retried|retry/i)).toBeTruthy();
  });

  it("renders every RunStatus without throwing", () => {
    const statuses: Job["status"][] = [
      "queued", "claimed", "running", "retry_wait", "succeeded", "failed", "manual_retry", "cancelled",
    ];
    for (const status of statuses) {
      const { unmount } = render(
        <RescanProgress job={makeJob({ status })} summary={makeSummary()} />,
      );
      expect(screen.getByTestId("rescan-progress")).toBeTruthy();
      unmount();
    }
  });
});

// ── SelectiveRescanDialog ─────────────────────────────────────────────────
describe("SelectiveRescanDialog requires explicit human confirmation", () => {
  it("shows computed affected/carried counts and provider/cost wording from API state", () => {
    render(
      <SelectiveRescanDialog
        isOpen
        summary={makeSummary({ affectedElementCount: 4, carriedForwardItemCount: 5, providerWorkEstimate: 12 })}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("4");
    expect(dialog.textContent).toContain("5");
    expect(dialog.textContent).toContain("12");
    expect(dialog.textContent).toMatch(/provider|search calls|cost/i);
  });

  it("does not auto-start; only the confirm button triggers the rescan", () => {
    const onConfirm = vi.fn();
    render(
      <SelectiveRescanDialog isOpen summary={makeSummary()} onConfirm={onConfirm} onClose={vi.fn()} />,
    );
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("invokes onConfirm exactly once when the human confirms", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <SelectiveRescanDialog isOpen summary={makeSummary()} onConfirm={onConfirm} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: /confirm|start/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

// ── ScriptUploadModal purpose ─────────────────────────────────────────────
describe("ScriptUploadModal derives copy from purpose", () => {
  const baseProps = {
    isOpen: true,
    onClose: vi.fn(),
    orgSlug: "org-slug",
    projectId: "project-1",
    returnFocusRef: { current: null } as React.RefObject<HTMLElement>,
    successFocusRef: { current: null } as React.RefObject<HTMLElement>,
    onSuccess: vi.fn(),
  };

  it("uses revision copy when purpose is revision and never hard-codes 'Version one'", () => {
    render(<ScriptUploadModal {...baseProps} purpose="revision" />);
    const modal = screen.getByTestId("script-upload-modal");
    expect(modal.textContent?.toLowerCase()).toContain("revision");
    expect(modal.textContent).not.toContain("Version one");
  });

  it("defaults to the initial purpose", () => {
    render(<ScriptUploadModal {...baseProps} />);
    const modal = screen.getByTestId("script-upload-modal");
    expect(modal.textContent).not.toContain("Version one");
  });
});

// ── Query polling ─────────────────────────────────────────────────────────
describe("Job polling stops on terminal status", () => {
  it("classifies terminal vs nonterminal RunStatus", () => {
    expect(isTerminalRunStatus("succeeded")).toBe(true);
    expect(isTerminalRunStatus("failed")).toBe(true);
    expect(isTerminalRunStatus("cancelled")).toBe(true);
    expect(isTerminalRunStatus("running")).toBe(false);
    expect(isTerminalRunStatus("queued")).toBe(false);
    expect(isTerminalRunStatus("retry_wait")).toBe(false);
    expect(isTerminalRunStatus("manual_retry")).toBe(false);
    expect(isTerminalRunStatus("claimed")).toBe(false);
  });

  it("polls only while nonterminal and stops once terminal", () => {
    const options = jobQueryOptions({ ...SCOPE, jobId: "job-1" });
    const refetchInterval = options.refetchInterval as unknown as (query: {
      state: { data?: Job };
    }) => number | false;

    expect(refetchInterval({ state: { data: makeJob({ status: "running" }) } })).toBeGreaterThan(0);
    expect(refetchInterval({ state: { data: makeJob({ status: "succeeded" }) } })).toBe(false);
    expect(refetchInterval({ state: { data: makeJob({ status: "failed" }) } })).toBe(false);
    expect(refetchInterval({ state: { data: makeJob({ status: "cancelled" }) } })).toBe(false);
    // No data yet -> keep polling
    expect(refetchInterval({ state: {} })).toBeGreaterThan(0);
  });

  it("scopes query keys to tenant + project", () => {
    const key = scriptVersionKeys.list(SCOPE.orgSlug, SCOPE.projectId);
    expect(key).toContain(SCOPE.orgSlug);
    expect(key).toContain(SCOPE.projectId);
  });
});

// ── Mutation: accountable idempotency, no retry, job seeding ───────────────
describe("startSelectiveRescanMutationOptions", () => {
  let startSpy: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.resetModules();
    startSpy = vi.fn(async () => ({ ok: true, value: makeJob({ jobId: "job-seeded" }) }));
    vi.doMock("@clearcut/contracts", async (importOriginal) => {
      const actual = await importOriginal<Record<string, unknown>>();
      return { ...actual, api: { startSelectiveRescan: startSpy } };
    });
  });

  afterEach(() => {
    vi.doUnmock("@clearcut/contracts");
  });

  it("issues a fresh Idempotency-Key per invocation and never auto-retries", async () => {
    const { startSelectiveRescanMutationOptions: freshOptions } = await import(
      "../../../mutations/scriptVersionCommands"
    );
    const qc = new QueryClient();
    const options = freshOptions({ ...SCOPE, versionId: "v-2", queryClient: qc });

    expect(options.retry).toBe(false);

    await options.mutationFn!();
    await options.mutationFn!();

    expect(startSpy).toHaveBeenCalledTimes(2);
    const firstKey = startSpy.mock.calls[0][0].headers["Idempotency-Key"];
    const secondKey = startSpy.mock.calls[1][0].headers["Idempotency-Key"];
    expect(firstKey).toBeTruthy();
    expect(secondKey).toBeTruthy();
    expect(firstKey).not.toBe(secondKey);
    expect(startSpy.mock.calls[0][0].params).toMatchObject({
      orgId: SCOPE.orgSlug,
      projectId: SCOPE.projectId,
      versionId: "v-2",
    });
  });

  it("seeds the returned job into the exact job query cache on success", async () => {
    const { startSelectiveRescanMutationOptions: freshOptions } = await import(
      "../../../mutations/scriptVersionCommands"
    );
    const { jobQueryOptions: freshJobOptions } = await import("../../../queries/scriptVersions");
    const qc = new QueryClient();
    const options = freshOptions({ ...SCOPE, versionId: "v-2", queryClient: qc });

    const job = makeJob({ jobId: "job-seeded" });
    options.onSuccess!(job);

    const seeded = qc.getQueryData(
      freshJobOptions({ ...SCOPE, jobId: "job-seeded" }).queryKey,
    );
    expect(seeded).toEqual(job);
  });
});

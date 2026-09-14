// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "@clearcut/contracts";
import { DetectionRecovery } from "../../src/features/operations/DetectionRecovery";
vi.mock("@tanstack/react-router", () => ({
  Link: ({ search, children }: any) => <a href={`?${new URLSearchParams(search)}`}>{children}</a>,
}));
vi.mock("@clearcut/contracts", () => ({ api: { listJobs: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function mount(jobs: unknown[]) {
  vi.mocked(api.listJobs).mockResolvedValue({ ok: true, value: jobs } as any);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <DetectionRecovery orgSlug="org" projectId="project" versionId="v2" />
  </QueryClientProvider>);
}
it("recovers a failed persisted check for the displayed version, ignoring other jobs", async () => {
  mount([
    { jobId: "wrong", jobType: "detection", target: { type: "script_version", id: "v1" }, status: "failed" },
    { jobId: "research", jobType: "research", target: { type: "script_version", id: "v2" }, status: "failed" },
    { canRetry: true, jobId: "failed-check", jobType: "detection", target: { type: "script_version", id: "v2" }, status: "failed" },
  ]);
  const link = await screen.findByRole("link", { name: "Review failed check and retry" });
  expect(link.getAttribute("href")).toContain("jobId=failed-check");
  expect(link.getAttribute("href")).toContain("versionId=v2");
});
it("offers the existing start flow when this version has no check", async () => {
  mount([]);
  const link = await screen.findByRole("link", { name: "Run script check" });
  expect(link.getAttribute("href")).not.toContain("jobId");
});
it("keeps completed checks accessible without offering another scan", async () => {
  mount([{ jobId: "done", jobType: "detection", target: { type: "script_version", id: "v2" }, status: "succeeded" }]);
  expect(await screen.findByRole("link", { name: "View check results" })).toBeTruthy();
});
it("does not treat a failed job lookup as an unscanned script", async () => {
  mount([]);
  vi.mocked(api.listJobs).mockResolvedValue({ ok: false, error: { message: "Unavailable" } } as any);
  cleanup();
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <DetectionRecovery orgSlug="org" projectId="project" versionId="v2" />
  </QueryClientProvider>);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByRole("link")).toBeNull();
});

it("finds a check beyond the first page of research jobs", async () => {
  mount([]);
  vi.mocked(api.listJobs)
    .mockResolvedValueOnce({ ok: true, value: [], meta: { nextCursor: "older" } } as any)
    .mockResolvedValueOnce({ ok: true, value: [{ jobId: "old-check", jobType: "detection", target: { type: "script_version", id: "v2" }, status: "failed", canRetry: true }] } as any);
  cleanup();
  render(<QueryClientProvider client={new QueryClient()}>
    <DetectionRecovery orgSlug="org" projectId="project" versionId="v2" />
  </QueryClientProvider>);
  expect((await screen.findByRole("link", { name: "Review failed check and retry" })).getAttribute("href")).toContain("jobId=old-check");
  expect(api.listJobs).toHaveBeenLastCalledWith({ params: { orgId: "org", projectId: "project" }, query: { limit: 100, cursor: "older" } });
});

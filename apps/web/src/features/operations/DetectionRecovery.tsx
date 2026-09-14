import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, type Job } from "@clearcut/contracts";

/** Recover the persisted check without uploading again or creating a second job. */
export function DetectionRecovery({ orgSlug, projectId, versionId }: {
  orgSlug: string;
  projectId: string;
  versionId: string;
}) {
  const jobs = useQuery({
    queryKey: ["detection-recovery", orgSlug, projectId, versionId],
    queryFn: async () => {
      const matches: Job[] = [];
      let cursor: string | undefined;
      do {
        const result = await api.listJobs({
          params: { orgId: orgSlug, projectId }, query: { limit: 100, cursor },
        });
        if (!result.ok) throw new Error(result.error.message);
        matches.push(...result.value.filter((job) => job.jobType === "detection" &&
          job.target.type === "script_version" && job.target.id === versionId));
        cursor = result.meta?.nextCursor ?? undefined;
      } while (cursor);
      return matches.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    refetchInterval: 5000,
  });
  if (jobs.isPending) return <p className="small muted" role="status">Loading script check…</p>;
  if (jobs.isError) return <div role="alert" className="small">
    Could not load script check status. <button type="button" className="button button-secondary button-sm"
      onClick={() => void jobs.refetch()}>Try loading again</button>
  </div>;
  const job = jobs.data[0];
  const label = !job ? "Run script check"
    : job.status === "failed" ? (job.canRetry ? "Review failed check and retry" : "Review failed check")
    : job.status === "manual_retry" || job.status === "cancelled" ? "Resume script check"
    : job.status === "succeeded" ? "View check results" : "View running check";
  return <Link className="button button-secondary" to="/o/$orgSlug/projects/new"
    params={{ orgSlug }} search={{ projectId, versionId, ...(job ? { jobId: job.jobId } : {}) }}>
    {label}
  </Link>;
}

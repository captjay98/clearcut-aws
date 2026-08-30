import React, { useState, useEffect } from "react";
import { ReportPage } from "../../../../../features/report/ReportPage.tsx";
import { loadReportStatus } from "../../../../../lib/loaders.ts";

export function ProjectReportRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string };
}) {
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    loadReportStatus(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01"
    ).then(setReport);
  }, [params?.orgSlug, params?.projectId]);

  return <ReportPage />;
}

import React, { useState, useEffect } from "react";
import { WatchPage } from "../../../../../features/watch/WatchPage.tsx";
import { loadWatchConfig } from "../../../../../lib/loaders.ts";

export function ProjectWatchRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string };
}) {
  const [config, setConfig] = useState<any>(null);

  useEffect(() => {
    loadWatchConfig(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01"
    ).then(setConfig);
  }, [params?.orgSlug, params?.projectId]);

  return <WatchPage />;
}

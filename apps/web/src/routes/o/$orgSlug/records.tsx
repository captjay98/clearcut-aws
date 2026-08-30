import React, { useState, useEffect } from "react";
import { RecordsPage } from "../../../features/records/RecordsPage.tsx";
import { loadRecords } from "../../../lib/loaders.ts";

export function OrgRecordsRoute({ params }: { params?: { orgSlug: string } }) {
  const [records, setRecords] = useState<any[]>([]);

  useEffect(() => {
    loadRecords(params?.orgSlug || "acme-films").then(setRecords);
  }, [params?.orgSlug]);

  return <RecordsPage />;
}

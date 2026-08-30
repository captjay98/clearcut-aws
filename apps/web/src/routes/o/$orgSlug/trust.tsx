import React, { useState, useEffect } from "react";
import { TrustPage } from "../../../features/trust/TrustPage.tsx";
import { loadTrustAndRubric } from "../../../lib/loaders.ts";

export function OrgTrustRoute({ params }: { params?: { orgSlug: string } }) {
  const [trustData, setTrustData] = useState<any>(null);

  useEffect(() => {
    loadTrustAndRubric(params?.orgSlug || "acme-films").then(setTrustData);
  }, [params?.orgSlug]);

  return <TrustPage trustData={trustData} />;
}

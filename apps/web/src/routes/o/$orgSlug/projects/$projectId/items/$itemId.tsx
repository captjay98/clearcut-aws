import React, { useState, useEffect } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";
import { ClaimTable } from "../../../../../../features/evidence/ClaimTable.tsx";
import { CommentThread } from "../../../../../../features/evidence/CommentThread.tsx";
import { loadItemDetail } from "../../../../../../lib/loaders.ts";

export function ItemDetailRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string; itemId: string };
}) {
  const [item, setItem] = useState<any>(null);

  useEffect(() => {
    loadItemDetail(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01",
      params?.itemId || "item-01"
    ).then(setItem);
  }, [params?.orgSlug, params?.projectId, params?.itemId]);

  return (
    <Page
      title="Clearance Item: Coca-Cola"
      subtitle="Trademarks & Brand Names • Scene 1, Line 12"
      trail={[
        { label: "Overview", href: "../.." },
        { label: "Items", href: ".." },
        { label: "Coca-Cola" },
      ]}
    >
      <div className="space-y-6">
        <Card title="Item Details & Context">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Detected product placement risk for &ldquo;CAN OF COCA-COLA&rdquo; in dialogue and action description.
          </p>
        </Card>
        <Card title="Cited Evidence Claims">
          <ClaimTable />
        </Card>
        <Card title="Review Discussion">
          <CommentThread />
        </Card>
      </div>
    </Page>
  );
}

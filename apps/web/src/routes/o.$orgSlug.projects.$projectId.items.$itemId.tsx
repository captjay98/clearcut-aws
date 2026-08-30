import React, { useState } from "react";
import { Page, Card } from "@clearcut/design-system";
import { ClaimTable } from "../features/evidence/ClaimTable.tsx";
import { DecisionDialog } from "../features/evidence/DecisionDialog.tsx";
import { CommentThread } from "../features/evidence/CommentThread.tsx";

export function ItemDetailRoute() {
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  return (
    <Page
      title="Item Detail: Coca-Cola"
      subtitle="Products & Trademarks • Scene 1"
      trail={[
        { label: "Overview", href: ".." },
        { label: "Items", href: "." },
        { label: "Coca-Cola" },
      ]}
      actions={
        <button
          type="button"
          onClick={() => setIsDialogOpen(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm font-medium"
        >
          Record Governed Decision
        </button>
      }
    >
      <Card title="Admitted Evidence & Provenance">
        <ClaimTable
          claims={[
            {
              claimId: "1",
              claimText: "Active registered trademark owned by The Coca-Cola Company.",
              stance: "supports",
              authorityTier: "primary_official",
              sourceUrl: "https://uspto.gov/trademarks",
              sourceDomain: "uspto.gov",
              excerpt: "Registration No. 0224376 for Coca-Cola.",
            },
          ]}
        />
      </Card>

      <Card title="Review Discussion">
        <CommentThread
          comments={[
            {
              id: "c1",
              authorName: "Sarah Clearance",
              content: "Verified trademark registration is active. Needs Greeking or licensing.",
              createdAt: "10 mins ago",
            },
          ]}
          onAddComment={() => {}}
        />
      </Card>

      <DecisionDialog
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSubmit={() => {}}
        itemText="Coca-Cola"
      />
    </Page>
  );
}

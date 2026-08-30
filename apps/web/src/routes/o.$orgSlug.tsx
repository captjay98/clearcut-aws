import React from "react";
import { Sidebar } from "../components/navigation/Sidebar.tsx";

interface OrgLayoutProps {
  orgSlug: string;
  activePath?: string;
  children?: React.ReactNode;
}

export function OrgLayout({ orgSlug, activePath = "projects", children }: OrgLayoutProps) {
  return (
    <div className="flex-1 flex w-full">
      <Sidebar orgSlug={orgSlug} activePath={activePath} />
      <div className="flex-1 overflow-auto">{children}</div>
    </div>
  );
}

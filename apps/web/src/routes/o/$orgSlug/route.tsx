import React from "react";
import { Header } from "../../../components/navigation/Header.tsx";
import { Sidebar } from "../../../components/navigation/Sidebar.tsx";

export function OrgLayout({ children }: { children?: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
      <Header currentOrgSlug="acme-films" userEmail="reviewer@acmefilms.com" userRole="Reviewer" />
      <div className="flex-1 flex">
        <Sidebar activeOrgSlug="acme-films" />
        <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  );
}

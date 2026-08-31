import React from "react";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "../components/theme/ThemeProvider";

export interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
});

function RootComponent() {
  return (
    <ThemeProvider>
      <div
        id="root-container"
        data-clearcut-app="react"
        className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans"
      >
        <Outlet />
      </div>
    </ThemeProvider>
  );
}

export function RootLayout({ children }: { children?: React.ReactNode }) {
  return (
    <ThemeProvider>
      <div
        data-clearcut-app="react"
        className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans"
      >
        {children}
      </div>
    </ThemeProvider>
  );
}

export default RootComponent;

import React, { useEffect, useState } from "react";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";

export interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
});

function RootComponent() {
  const [theme, setTheme] = useState<"day-shoot" | "night-shoot">("day-shoot");

  useEffect(() => {
    const saved = localStorage.getItem("clearcut-theme");
    if (saved === "night-shoot" || saved === "day-shoot") {
      setTheme(saved);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "day-shoot" ? "night-shoot" : "day-shoot";
    setTheme(next);
    localStorage.setItem("clearcut-theme", next);
  };

  return (
    <div
      id="root-container"
      data-clearcut-app="react"
      data-theme={theme}
      className="min-h-screen flex flex-col bg-slate-900 text-slate-100 font-sans"
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-amber-600 focus:text-white focus:rounded"
      >
        Skip to main content
      </a>
      <div id="main-content" className="flex-1 flex flex-col">
        <Outlet />
      </div>
    </div>
  );
}

export function RootLayout({ children }: { children?: React.ReactNode }) {
  return (
    <div
      data-clearcut-app="react"
      className="min-h-screen flex flex-col bg-slate-900 text-slate-100 font-sans"
    >
      <div className="flex-1 flex flex-col">{children}</div>
    </div>
  );
}

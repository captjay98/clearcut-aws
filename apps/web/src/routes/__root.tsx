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
      {/* Canvas, ink and typography come from the design system's base layer on
          body, exactly as in the canonical mock, so this stays a bare boundary
          marker rather than restating the theme. */}
      <div id="root-container" data-clearcut-app="react">
        <Outlet />
      </div>
    </ThemeProvider>
  );
}

export function RootLayout({ children }: { children?: React.ReactNode }) {
  return (
    <ThemeProvider>
      <div data-clearcut-app="react">{children}</div>
    </ThemeProvider>
  );
}

export default RootComponent;

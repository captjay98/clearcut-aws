export interface RouteStateFixture {
  routeId: string;
  path: string;
  state: "empty" | "loading" | "populated" | "error" | "unauthorized";
  theme: "day-shoot" | "night-shoot";
  viewport: { width: number; height: number };
}

export const CANONICAL_ROUTE_STATES: RouteStateFixture[] = [
  {
    routeId: "sign-in",
    path: "/auth/sign-in",
    state: "empty",
    theme: "day-shoot",
    viewport: { width: 1440, height: 900 },
  },
  {
    routeId: "onboarding",
    path: "/onboarding",
    state: "empty",
    theme: "day-shoot",
    viewport: { width: 1440, height: 900 },
  },
  {
    routeId: "projects-list",
    path: "/o/paramount/projects",
    state: "populated",
    theme: "day-shoot",
    viewport: { width: 1440, height: 900 },
  },
  {
    routeId: "project-new-wizard",
    path: "/o/paramount/projects/new",
    state: "empty",
    theme: "night-shoot",
    viewport: { width: 768, height: 1024 },
  },
  {
    routeId: "team-access",
    path: "/o/paramount/team",
    state: "populated",
    theme: "day-shoot",
    viewport: { width: 375, height: 667 },
  },
];

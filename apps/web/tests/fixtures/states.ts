export interface RouteStateFixture {
  routeId: string;
  path: string;
  state: "empty" | "loading" | "populated" | "error" | "unauthorized";
  theme: "day-shoot" | "night-shoot";
  viewport: { width: number; height: number };
}

export const INITIAL_SEED_STATE = {
  projects: [
    {
      id: "proj-01",
      name: "The Last Reel",
      title: "The Last Reel",
      description: "Feature screenplay pre-clearance workspace",
    },
  ],
  notifications: [
    {
      id: "notif-01",
      tier: "urgent",
      title: "Rewrite Proposal Approved",
      message: "Greeking replacement for CC-104 approved by Bob Reviewer",
      createdAt: "2026-08-30T15:20:10Z",
    },
  ],
};

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

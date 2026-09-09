export * from "./components/Page.tsx";
export * from "./components/Card.tsx";
export * from "./components/Badge.tsx";
export * from "./components/Banner.tsx";
export * from "./components/StatGrid.tsx";
export * from "./components/EmptyState.tsx";
export * from "./components/Progress.tsx";
export * from "./adapters/dialog.tsx";
export * from "./adapters/combobox.tsx";

export const THEMES = {
  SCRIPT: "script",
  NIGHT: "night",
} as const;

export type Theme = typeof THEMES[keyof typeof THEMES];

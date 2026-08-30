/**
 * ClearCut Design System Tokens and Primitives
 * Source of truth: misc/clearcut-flow
 */

export const THEMES = {
  DAY_SHOOT: 'day-shoot',
  NIGHT_SHOOT: 'night-shoot',
} as const;

export type Theme = typeof THEMES[keyof typeof THEMES];

export const TOKENS = {
  colors: {
    bgDay: '#ffffff',
    bgNight: '#0d1117',
    primary: '#1d4ed8',
    danger: '#dc2626',
    warning: '#f59e0b',
    success: '#10b981',
  },
  typography: {
    fontSans: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontMono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  },
};

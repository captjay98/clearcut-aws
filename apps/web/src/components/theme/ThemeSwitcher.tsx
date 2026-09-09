import React from "react";
import { useTheme } from "./ThemeProvider";

export function ThemeSwitcher() {
  const { theme, toggleTheme } = useTheme();

  const label = theme === "night" ? "Night (Dark)" : "Script (Light)";

  const icon = "◐";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Toggle Shoot Theme, currently ${label}`}
      className="inline-flex items-center space-x-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500"
    >
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

import React from "react";

interface HeaderProps {
  currentOrg?: string;
  theme?: string;
  onToggleTheme?: () => void;
}

export function Header({ currentOrg, theme = "day-shoot", onToggleTheme }: HeaderProps) {
  return (
    <header className="h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <a href="/" className="font-bold text-blue-600 dark:text-blue-400 text-lg">
          ClearCut
        </a>
        {currentOrg && (
          <span className="text-xs px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded font-medium text-slate-600 dark:text-slate-300">
            {currentOrg}
          </span>
        )}
      </div>
      <div className="flex items-center space-x-3">
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label="Toggle Shoot Theme"
          className="text-xs px-2.5 py-1 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          {theme === "night-shoot" ? "🌙 Night Shoot" : "☀️ Day Shoot"}
        </button>
      </div>
    </header>
  );
}

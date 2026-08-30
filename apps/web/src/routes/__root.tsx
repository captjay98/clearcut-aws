import React, { useState } from "react";
import { Header } from "../components/navigation/Header.tsx";

interface RootProps {
  children?: React.ReactNode;
}

export function RootLayout({ children }: RootProps) {
  const [theme, setTheme] = useState<"day-shoot" | "night-shoot">("day-shoot");

  const toggleTheme = () => {
    setTheme((prev) => (prev === "day-shoot" ? "night-shoot" : "day-shoot"));
  };

  return (
    <div
      data-theme={theme}
      className="min-h-screen flex flex-col bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans"
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded"
      >
        Skip to main content
      </a>
      <Header theme={theme} onToggleTheme={toggleTheme} />
      <div className="flex-1 flex">{children}</div>
    </div>
  );
}

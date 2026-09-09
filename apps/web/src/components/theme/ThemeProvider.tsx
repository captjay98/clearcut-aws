import React, { createContext, useContext, useEffect, useState } from "react";

export type Theme = "script" | "night";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// Migrate legacy stored values to the mock's two-theme vocabulary.
function normalizeTheme(saved: string | null): Theme {
  if (saved === "script" || saved === "day-shoot") {
    return "script";
  }
  if (saved === "night" || saved === "night-shoot" || saved === "high-contrast") {
    return "night";
  }
  return "script";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      return normalizeTheme(localStorage.getItem("clearcut_theme"));
    }
    return "script";
  });

  const applyTheme = (t: Theme) => {
    setThemeState(t);
    if (typeof window !== "undefined") {
      localStorage.setItem("clearcut_theme", t);
      document.documentElement.setAttribute("data-theme", t);
      document.documentElement.classList.remove("script", "night", "dark");
      document.documentElement.classList.add(t);
      if (t === "night") {
        document.documentElement.classList.add("dark");
      }
    }
  };

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    applyTheme(theme === "script" ? "night" : "script");
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme: applyTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}

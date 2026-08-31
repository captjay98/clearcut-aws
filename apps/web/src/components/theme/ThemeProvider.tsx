import React, { createContext, useContext, useEffect, useState } from "react";

export type Theme = "day-shoot" | "night-shoot" | "high-contrast";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("clearcut_theme") as Theme | null;
      if (saved === "day-shoot" || saved === "night-shoot" || saved === "high-contrast") {
        return saved;
      }
    }
    return "day-shoot";
  });

  const applyTheme = (t: Theme) => {
    setThemeState(t);
    if (typeof window !== "undefined") {
      localStorage.setItem("clearcut_theme", t);
      document.documentElement.setAttribute("data-theme", t);
      document.documentElement.classList.remove("day-shoot", "night-shoot", "high-contrast", "dark");
      document.documentElement.classList.add(t);
      if (t === "night-shoot" || t === "high-contrast") {
        document.documentElement.classList.add("dark");
      }
    }
  };

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    if (theme === "day-shoot") {
      applyTheme("night-shoot");
    } else if (theme === "night-shoot") {
      applyTheme("high-contrast");
    } else {
      applyTheme("day-shoot");
    }
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

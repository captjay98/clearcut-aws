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
      // The design system keys every theme off [data-theme], the same as the
      // canonical mock. The previous `dark` class existed only to drive
      // Tailwind's class dark-mode strategy and has no styling attached now.
      document.documentElement.setAttribute("data-theme", t);
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", t === "night" ? "#14161b" : "#f6f3ea");
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

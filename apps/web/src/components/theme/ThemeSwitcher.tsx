import React from "react";
import { useTheme } from "./ThemeProvider";

/**
 * The mock exposes appearance as a single bare icon button in the header
 * (`data-action="open-appearance"`), labelled for assistive technology rather
 * than carrying visible text.
 */
export function ThemeSwitcher() {
  const { theme, toggleTheme } = useTheme();
  const label = theme === "night" ? "Night" : "Script";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="icon-button is-bare"
      data-testid="theme-switcher"
      aria-label={`Choose workspace appearance, currently ${label} theme`}
    >
      <span aria-hidden="true">◐</span>
    </button>
  );
}

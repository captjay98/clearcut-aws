// @vitest-environment node

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss from "tailwindcss";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "../..");
const indexCssPath = path.join(webRoot, "src", "index.css");
const tailwindConfigPath = path.join(webRoot, "tailwind.config.js");

/**
 * The runtime emits exactly these three theme names (ThemeProvider + index.html).
 * The stylesheet MUST define the core visual tokens for each of the three so that
 * background, foreground and font never fall back to unstyled UA defaults.
 */
const EMITTED_THEMES = ["day-shoot", "night-shoot", "high-contrast"] as const;
const CORE_TOKENS = ["--canvas", "--ink", "--sans"] as const;

function tokenBlockFor(css: string, theme: string): string {
  // Match a selector list that includes :root[data-theme="<theme>"] and capture its block.
  const re = new RegExp(
    `(?:^|[},])\\s*([^{}]*\\[data-theme=["']${theme}["']\\][^{}]*)\\{([^{}]*)\\}`,
    "m",
  );
  const match = css.match(re);
  return match ? match[2] : "";
}

describe("Theme tokens resolve for every emitted theme", () => {
  const css = readFileSync(indexCssPath, "utf8");

  for (const theme of EMITTED_THEMES) {
    it(`defines all core tokens for data-theme="${theme}"`, () => {
      const block = tokenBlockFor(css, theme);
      expect(block, `no token block found for data-theme="${theme}"`).not.toBe("");
      for (const token of CORE_TOKENS) {
        const decl = new RegExp(`${token}\\s*:\\s*[^;]+;`);
        expect(
          decl.test(block),
          `token ${token} is unset for data-theme="${theme}"`,
        ).toBe(true);
      }
    });
  }

  it("does not key core tokens to the stale theme names", () => {
    // The old (broken) selectors were data-theme="script" / "night".
    expect(tokenBlockFor(css, "script")).toBe("");
    expect(tokenBlockFor(css, "night")).toBe("");
  });
});

describe("Utility CSS pipeline generates every emitted utility/variant", () => {
  // A representative sample of the utility vocabulary actually used across the app:
  // a base utility, a color utility, a layout utility, plus dark:/hover:/focus:/sm: variants.
  const fixture = `
    <div class="flex min-h-screen space-y-6 bg-slate-950 text-slate-100
                dark:bg-slate-900 hover:bg-amber-700 focus:ring-2 sm:px-6"></div>
  `;

  async function compile(): Promise<string> {
    const input = "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n";
    const config = {
      content: [{ raw: fixture, extension: "html" }],
      darkMode: "class" as const,
      theme: { extend: {} },
      plugins: [],
    };
    const result = await postcss([tailwindcss(config as never)]).process(input, {
      from: undefined,
    });
    return result.css;
  }

  it("emits a representative base/color/layout utility", async () => {
    const out = await compile();
    expect(out).toMatch(/\.flex\s*\{/);
    expect(out).toContain(".bg-slate-950");
    expect(out).toContain(".min-h-screen");
  });

  it("emits dark, hover, focus and responsive variants", async () => {
    const out = await compile();
    expect(out).toContain(".dark\\:bg-slate-900");
    expect(out).toContain(".hover\\:bg-amber-700");
    expect(out).toContain(".focus\\:ring-2");
    expect(out).toMatch(/@media \(min-width: 640px\)/);
  });

  it("wires the emitted themes' dark mode to the class strategy", () => {
    const configSource = readFileSync(tailwindConfigPath, "utf8");
    // ThemeProvider toggles a `dark` class for night-shoot/high-contrast, so the
    // pipeline must resolve dark: variants against a class, not the OS preference.
    expect(configSource).toMatch(/darkMode\s*:\s*["']class["']/);
  });
});

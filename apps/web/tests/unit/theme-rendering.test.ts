// @vitest-environment node

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "../..");
const indexCssPath = path.join(webRoot, "src", "index.css");

/**
 * The runtime emits exactly these two theme names (ThemeProvider + index.html),
 * matching the mock's vocabulary. The stylesheet MUST define the core visual
 * tokens for each so that background, foreground and font never fall back to
 * unstyled UA defaults.
 */
const EMITTED_THEMES = ["script", "night"] as const;
const ABSENT_THEMES = ["day-shoot", "night-shoot", "high-contrast"] as const;
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
    // The old (invented) selectors were day-shoot / night-shoot / high-contrast.
    for (const theme of ABSENT_THEMES) {
      expect(
        tokenBlockFor(css, theme),
        `stale theme block for data-theme="${theme}" should be removed`,
      ).toBe("");
    }
  });
});

/**
 * The workspace stylesheet must stay a single plain stylesheet.
 *
 * Tailwind v3 treated `@layer base`, `@layer components` and `@layer utilities`
 * as its own directives rather than CSS cascade layers. That had two effects
 * that silently deleted most of the design system:
 *
 *  1. Component rules inside those blocks were tree-shaken unless the class name
 *     already appeared in the scanned markup, so `.badge` and `.banner`
 *     resolved to nothing at all.
 *  2. The hoisted rules landed outside the declared cascade layers, letting the
 *     unlayered preflight `button { background-color: transparent }` override
 *     `.button-primary`.
 *
 * Reintroducing a Tailwind directive here would bring both back, so this guards
 * the stylesheet rather than a utility pipeline.
 */
describe("Workspace stylesheet is a single plain design-system stylesheet", () => {
  const css = readFileSync(indexCssPath, "utf8");

  it("declares no Tailwind directives", () => {
    expect(css).not.toMatch(/@tailwind\b/);
    expect(css).not.toMatch(/@apply\b/);
  });

  it("declares the cascade layer order before any layered rule", () => {
    const statement = css.indexOf("@layer reset, tokens, base, layout");
    const firstBlock = css.indexOf("@layer reset {");
    expect(statement).toBeGreaterThan(-1);
    expect(firstBlock).toBeGreaterThan(statement);
  });

  it("retains the component rules Tailwind used to tree-shake", () => {
    // Each of these resolved to no styling at all while Tailwind owned the
    // component layer, because no .tsx referenced the class yet.
    for (const selector of [".badge", ".banner", ".button-primary", ".card", ".page"]) {
      expect(css.includes(`${selector} {`) || css.includes(`${selector},`)).toBe(true);
    }
  });
});

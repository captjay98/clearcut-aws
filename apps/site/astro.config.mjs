import { defineConfig } from "astro/config";

// The public marketing site renders the canonical mock markup and is styled
// entirely by the design system (misc/clearcut-flow/assets/app.css, published as
// @clearcut/design-system/tokens.css). No utility framework is used here: the
// mock is a plain stylesheet, and adding Tailwind's preflight alongside the
// design system's own reset reordered the cascade so generic element resets beat
// the more specific marketing classes.
export default defineConfig({});

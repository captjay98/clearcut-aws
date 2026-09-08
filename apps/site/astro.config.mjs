import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

// The public marketing site uses the same Tailwind utility vocabulary as the
// workspace, so it needs a real utility pipeline. `applyBaseStyles: false` lets
// our own global.css own the @tailwind directives and load the design tokens.
export default defineConfig({
  integrations: [
    tailwind({
      applyBaseStyles: false,
    }),
  ],
});

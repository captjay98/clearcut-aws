import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "path";

export default defineConfig({
  plugins: [
    TanStackRouterVite({
      routesDirectory: "./src/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
    }),
    react(),
  ],
  server: {
    port: 5173,
    host: "127.0.0.1",
  },
  resolve: {
    alias: {
      "@clearcut/design-system": path.resolve(__dirname, "../../packages/design-system/src/index.ts"),
      "@clearcut/contracts": path.resolve(__dirname, "../../packages/contracts/generated/typescript/index.ts"),
    },
  },
});

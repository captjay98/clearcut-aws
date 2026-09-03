import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vitest/config";

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
    proxy: {
      "/api": {
        target: process.env.CLEARCUT_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
      },
    },
  },
  resolve: {
    alias: {
      "@clearcut/design-system": path.resolve(
        __dirname,
        "../../packages/design-system/src/index.ts",
      ),
      "@clearcut/contracts": path.resolve(
        __dirname,
        "../../packages/contracts/generated/typescript/index.ts",
      ),
    },
  },
  test: {
    include: [
      "tests/unit/**/*.test.{ts,tsx}",
      "tests/config/**/*.test.ts",
    ],
  },
});

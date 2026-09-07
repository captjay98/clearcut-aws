import { createRouter as createTanStackRouter } from "@tanstack/react-router";
import { queryClient } from "./integrations/tanstack-query/root-provider";
import { routeTree } from "./routeTree.gen";

export function createRouter() {
  return createTanStackRouter({
    routeTree,
    basepath: "/app",
    context: {
      queryClient,
    },
    defaultPreload: "intent",
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createRouter>;
  }
}

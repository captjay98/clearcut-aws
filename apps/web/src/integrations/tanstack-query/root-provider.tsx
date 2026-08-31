import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        retry: (failureCount, error: any) => {
          // Governed invariant: ordinary reads retry only typed retryable failures
          if (error && error.retryable === false) return false;
          if (error && (error.code === "authentication_required" || error.code === "permission_denied" || error.code === "not_found")) {
            return false;
          }
          return failureCount < 2;
        },
      },
      mutations: {
        // Governed writes never retry automatically
        retry: false,
      },
    },
  });
}

export const queryClient = createQueryClient();

export function RootQueryProvider({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

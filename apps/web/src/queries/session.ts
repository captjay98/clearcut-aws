import { queryOptions } from "@tanstack/react-query";
import { api, type SessionContext } from "@clearcut/contracts";

type SessionClient = Pick<typeof api, "getSessionContext">;

export const sessionKeys = {
  context: () => ["session-context"] as const,
};

/**
 * The caller's own role, read from the server rather than inferred from the URL.
 *
 * Surfaces use it only to decide whether to *offer* a governed control. The
 * server remains the authority: a hidden button is a courtesy, not a boundary,
 * and every governed write is authorized again server-side.
 */
export function sessionContextQueryOptions(client: SessionClient = api) {
  return queryOptions({
    queryKey: sessionKeys.context(),
    queryFn: async (): Promise<SessionContext> => {
      const result = await client.getSessionContext();
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value;
    },
    staleTime: 60_000,
  });
}

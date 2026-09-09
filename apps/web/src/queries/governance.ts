import { queryOptions } from "@tanstack/react-query";
import {
  api,
  type HealthResponse,
  type OrganizationSettings,
  type ProtectedConfiguration,
} from "@clearcut/contracts";

type ProtectedConfigurationClient = Pick<typeof api, "listProtectedConfigurations">;
type OrganizationSettingsClient = Pick<typeof api, "getOrganizationSettings">;

export const governanceKeys = {
  protectedConfigurations: (orgId: string) =>
    ["protected-configurations", orgId] as const,
  organizationSettings: (orgId: string) => ["organization-settings", orgId] as const,
};

/**
 * The organization's protected configuration bindings, newest first.
 *
 * Lifecycle is read from the server, never inferred: a `validated` row is the
 * only one that may be activated and an `active` row is immutable, so the
 * available action follows the persisted lifecycle rather than local state.
 */
export function protectedConfigurationsQueryOptions(
  orgId: string,
  client: ProtectedConfigurationClient = api,
) {
  return queryOptions({
    queryKey: governanceKeys.protectedConfigurations(orgId),
    queryFn: async (): Promise<ProtectedConfiguration[]> => {
      const result = await client.listProtectedConfigurations({ params: { orgId } });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return [...(result.value ?? [])].sort(
        (left, right) =>
          new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
      );
    },
  });
}

export function organizationSettingsQueryOptions(
  orgId: string,
  client: OrganizationSettingsClient = api,
) {
  return queryOptions({
    queryKey: governanceKeys.organizationSettings(orgId),
    queryFn: async (): Promise<OrganizationSettings> => {
      const result = await client.getOrganizationSettings({ params: { orgId } });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value;
    },
  });
}


type HealthClient = Pick<typeof api, "getHealth">;

export const deploymentKeys = {
  health: () => ["deployment-health"] as const,
};

/**
 * The deployment's own account of which adapters and paid providers are active.
 *
 * The integrations view reads this rather than asserting that a provider is
 * "connected": a provider that is disabled is reported as disabled, and one the
 * deployment does not mention is not claimed either way.
 */
export function deploymentHealthQueryOptions(client: HealthClient = api) {
  return queryOptions({
    queryKey: deploymentKeys.health(),
    queryFn: async (): Promise<HealthResponse> => {
      const result = await client.getHealth();
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value;
    },
    staleTime: 60_000,
  });
}

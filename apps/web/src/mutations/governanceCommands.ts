import type { QueryClient } from "@tanstack/react-query";
import {
  api,
  type ApiError,
  type OrganizationSettings,
  type ProtectedConfiguration,
} from "@clearcut/contracts";
import { governanceKeys } from "../queries/governance";

type DraftClient = Pick<typeof api, "draftProtectedConfiguration">;
type ValidateClient = Pick<typeof api, "validateProtectedConfiguration">;
type ActivateClient = Pick<typeof api, "activateProtectedConfiguration">;
type SettingsClient = Pick<typeof api, "updateOrganizationSettings">;

/** A fresh, accountable idempotency key for a single human-triggered command. */
export function freshIdempotencyKey(prefix: string): string {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") {
    return `${prefix}-${cryptoObj.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function toCommandError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

/** True for the stale-version rejection that must surface, never auto-retry. */
export function isStaleVersionConflict(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { code?: string }).code === "conflict_stale_version"
  );
}

/* ── Protected configuration lifecycle ──────────────────────────────────── */

export interface DraftProtectedConfigurationInput {
  label?: string;
  policyVersion: string;
  promptVersion: string;
  rationale: string;
}

export async function executeDraftProtectedConfiguration(
  orgId: string,
  input: DraftProtectedConfigurationInput,
  client: DraftClient = api,
): Promise<ProtectedConfiguration> {
  const result = await client.draftProtectedConfiguration({
    params: { orgId },
    headers: { "Idempotency-Key": freshIdempotencyKey("protected-config-draft") },
    body: {
      ...(input.label ? { label: input.label } : {}),
      policyVersion: input.policyVersion,
      promptVersion: input.promptVersion,
      rationale: input.rationale,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeValidateProtectedConfiguration(
  orgId: string,
  configurationId: string,
  client: ValidateClient = api,
): Promise<{ valid: boolean; issues?: string[] }> {
  // No Idempotency-Key: unlike drafting, the contract does not declare one for
  // validation, and sending an undeclared header is not the place to invent one.
  const result = await client.validateProtectedConfiguration({
    params: { orgId, configurationId },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeActivateProtectedConfiguration(
  orgId: string,
  configurationId: string,
  client: ActivateClient = api,
): Promise<{ configurationId: string; status: string }> {
  const result = await client.activateProtectedConfiguration({
    params: { orgId, configurationId },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

async function invalidateProtectedConfigurations(
  queryClient: QueryClient,
  orgId: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: governanceKeys.protectedConfigurations(orgId),
  });
  // Activating or validating a protected configuration writes an audit event in
  // the same transaction, so the ledger view is stale too.
  await queryClient.invalidateQueries({ queryKey: ["records", orgId] });
}

export function draftProtectedConfigurationMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: DraftClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: DraftProtectedConfigurationInput) =>
      executeDraftProtectedConfiguration(orgId, input, client),
    onSuccess: () => invalidateProtectedConfigurations(queryClient, orgId),
  };
}

export function validateProtectedConfigurationMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: ValidateClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (configurationId: string) =>
      executeValidateProtectedConfiguration(orgId, configurationId, client),
    onSuccess: () => invalidateProtectedConfigurations(queryClient, orgId),
  };
}

export function activateProtectedConfigurationMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: ActivateClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (configurationId: string) =>
      executeActivateProtectedConfiguration(orgId, configurationId, client),
    onSuccess: () => invalidateProtectedConfigurations(queryClient, orgId),
  };
}

/* ── Organization settings ──────────────────────────────────────────────── */

export interface UpdateOrganizationSettingsInput {
  name: string;
  jurisdiction?: string;
  defaultMonitoringCadence: OrganizationSettings["defaultMonitoringCadence"];
  /** The version the editor was shown; a mismatch is rejected, not merged. */
  expectedVersion: number;
}

export async function executeUpdateOrganizationSettings(
  orgId: string,
  input: UpdateOrganizationSettingsInput,
  client: SettingsClient = api,
): Promise<OrganizationSettings> {
  const result = await client.updateOrganizationSettings({
    params: { orgId },
    headers: { "Idempotency-Key": freshIdempotencyKey("org-settings") },
    body: {
      name: input.name,
      ...(input.jurisdiction !== undefined ? { jurisdiction: input.jurisdiction } : {}),
      defaultMonitoringCadence: input.defaultMonitoringCadence,
      expectedVersion: input.expectedVersion,
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

/**
 * Settings are optimistically concurrent, so:
 *  - each save mints one fresh Idempotency-Key and never auto-retries;
 *  - a `conflict_stale_version` rejection refetches the authoritative record so
 *    the editor is re-based on what is actually stored. Retrying blind would
 *    overwrite whatever the other editor just saved.
 */
export function updateOrganizationSettingsMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: SettingsClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: UpdateOrganizationSettingsInput) =>
      executeUpdateOrganizationSettings(orgId, input, client),
    onSuccess: (settings: OrganizationSettings) => {
      queryClient.setQueryData(governanceKeys.organizationSettings(orgId), settings);
      void queryClient.invalidateQueries({ queryKey: ["records", orgId] });
    },
    onError: (error: unknown) => {
      if (!isStaleVersionConflict(error)) return;
      void queryClient.invalidateQueries({
        queryKey: governanceKeys.organizationSettings(orgId),
      });
    },
  };
}

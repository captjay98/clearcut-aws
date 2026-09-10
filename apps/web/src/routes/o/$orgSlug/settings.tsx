import React from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Banner,
  Card,
  DataTable,
  Page,
  Section,
  TabsBar,
} from "../../../components/ds";
import {
  deploymentHealthQueryOptions,
  organizationSettingsQueryOptions,
  protectedConfigurationsQueryOptions,
} from "../../../queries/governance";
import { sessionContextQueryOptions } from "../../../queries/session";
import { notificationDeliveryPreferenceQueryOptions } from "../../../queries/notifications";
import {
  activateProtectedConfigurationMutationOptions,
  draftProtectedConfigurationMutationOptions,
  isStaleVersionConflict,
  updateOrganizationSettingsMutationOptions,
  validateProtectedConfigurationMutationOptions,
} from "../../../mutations/governanceCommands";
import { setNotificationDeliveryPreferenceMutationOptions } from "../../../mutations/notificationCommands";
import { OrganizationProfileForm } from "../../../features/governance/OrganizationProfileForm";
import { NotificationDeliveryPreferenceForm } from "../../../features/settings/NotificationDeliveryPreferenceForm";
import { ProtectedConfigurationTable } from "../../../features/governance/ProtectedConfigurationTable";
import { ProtectedRulesBanner } from "../../../features/governance/ProtectedRulesBanner";
import { DraftConfigurationForm } from "../../../features/governance/DraftConfigurationForm";
import {
  canManageGovernance,
  canManageOrganizationSettings,
} from "../../../features/governance/capabilities";

type SettingsTab = "general" | "integrations" | "data" | "governance";

const SETTINGS_TABS = new Set<SettingsTab>([
  "general",
  "integrations",
  "data",
  "governance",
]);

interface SettingsSearch {
  tab: SettingsTab;
}

export const Route = createFileRoute("/o/$orgSlug/settings")({
  validateSearch: (search: Record<string, unknown>): SettingsSearch => ({
    tab:
      typeof search.tab === "string" && SETTINGS_TABS.has(search.tab as SettingsTab)
        ? (search.tab as SettingsTab)
        : "general",
  }),
  component: SettingsRoute,
});

function errorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

export function SettingsRoute() {
  const { orgSlug } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = useNavigate({ from: "/o/$orgSlug/settings" });
  const queryClient = useQueryClient();

  const sessionQuery = useQuery(sessionContextQueryOptions());
  const role = sessionQuery.data?.role ?? null;
  const canManageSettings = canManageOrganizationSettings(role);
  const canGovern = canManageGovernance(role);

  const settingsQuery = useQuery(organizationSettingsQueryOptions(orgSlug));
  const configurationsQuery = useQuery(
    protectedConfigurationsQueryOptions(orgSlug),
  );
  const healthQuery = useQuery(deploymentHealthQueryOptions());
  const deliveryPreferenceQuery = useQuery(
    notificationDeliveryPreferenceQueryOptions(orgSlug),
  );

  const saveSettings = useMutation(
    updateOrganizationSettingsMutationOptions(orgSlug, queryClient),
  );
  const saveDeliveryPreference = useMutation(
    setNotificationDeliveryPreferenceMutationOptions(orgSlug, queryClient),
  );
  const draftConfiguration = useMutation(
    draftProtectedConfigurationMutationOptions(orgSlug, queryClient),
  );
  const validateConfiguration = useMutation(
    validateProtectedConfigurationMutationOptions(orgSlug, queryClient),
  );
  const activateConfiguration = useMutation(
    activateProtectedConfigurationMutationOptions(orgSlug, queryClient),
  );

  const configurationPendingId =
    (validateConfiguration.isPending
      ? validateConfiguration.variables
      : activateConfiguration.isPending
        ? activateConfiguration.variables
        : undefined) ?? null;
  const configurationError =
    errorMessage(validateConfiguration.error) ??
    errorMessage(activateConfiguration.error);

  const deployment = healthQuery.data?.deployment;
  const paidProviders = deployment?.paidProvidersEnabled ?? [];

  return (
    <Page
      trail={[{ label: "Settings" }]}
      eyebrow="Organization"
      title="Settings"
      lede="Organization profile, integrations, what ClearCut stores, and the governance contracts in force."
    >
      <TabsBar
        label="Settings sections"
        active={tab}
        items={[
          { value: "general", label: "General" },
          { value: "integrations", label: "Integrations" },
          { value: "data", label: "Data & privacy" },
          { value: "governance", label: "Governance" },
        ]}
        onChange={(value) => {
          void navigate({ search: { tab: value as SettingsTab } });
        }}
      />

      <div className="gap-t-6">
        {/* ── General ──────────────────────────────────────────────────── */}
        {tab === "general" && (
          <Section
            title="Profile"
            description="The organization's own record. Every field here is stored and versioned; a save is rejected rather than merged if someone else saved first."
          >
            {settingsQuery.isPending ? (
              <p role="status" className="small muted">
                Loading organization settings…
              </p>
            ) : settingsQuery.isError ? (
              <Banner
                tone="is-danger"
                icon="⚠"
                title="Could not read the organization settings"
                message={`${errorMessage(settingsQuery.error)} No stored value has been guessed in the meantime.`}
                role="alert"
              />
            ) : settingsQuery.data ? (
              <OrganizationProfileForm
                settings={settingsQuery.data}
                canManage={canManageSettings}
                saving={saveSettings.isPending}
                staleConflict={isStaleVersionConflict(saveSettings.error)}
                error={errorMessage(saveSettings.error)}
                saved={saveSettings.isSuccess}
                onSave={(input) => saveSettings.mutate(input)}
              />
            ) : null}
          </Section>
        )}

        {/* ── Notifications (personal) ─────────────────────────────────── */}
        {tab === "general" && (
          <Section
            title="Notifications"
            description="Your own delivery channel for reviews, referrals and monitoring alerts. This is a personal preference — it grants nothing to anyone else and changes nothing for the organization."
          >
            {deliveryPreferenceQuery.isPending ? (
              <p role="status" className="small muted">
                Loading your notification preference…
              </p>
            ) : (
              <NotificationDeliveryPreferenceForm
                channel={deliveryPreferenceQuery.data?.channel ?? "in_app"}
                saving={saveDeliveryPreference.isPending}
                saved={saveDeliveryPreference.isSuccess}
                error={errorMessage(saveDeliveryPreference.error)}
                onChange={(channel) => saveDeliveryPreference.mutate(channel)}
              />
            )}
          </Section>
        )}
        {tab === "integrations" && (
          <Section
            title="Integrations"
            description="Credentials are environment-managed. This is the deployment's own account of which adapters are in use — not a claim that a provider is reachable."
          >
            {healthQuery.isPending ? (
              <p role="status" className="small muted">
                Reading the deployment profile…
              </p>
            ) : healthQuery.isError || !deployment ? (
              <Banner
                tone="is-danger"
                icon="⚠"
                title="Could not read the deployment profile"
                message={`${errorMessage(healthQuery.error) ?? "The deployment did not report its adapters."} No provider is reported as connected on the strength of its absence.`}
                role="alert"
              />
            ) : (
              <>
                <DataTable
                  caption="Adapters and providers reported by this deployment"
                  columns={[
                    { label: "Provider" },
                    { label: "Purpose" },
                    { label: "Status" },
                  ]}
                  rows={[
                    [
                      <strong>Gemini</strong>,
                      <span className="small muted">
                        Detection and rewrite proposals
                      </span>,
                      paidProviders.includes("gemini") ? (
                        <Badge tone="is-success">Enabled</Badge>
                      ) : (
                        <Badge tone="is-warning">Disabled by default</Badge>
                      ),
                    ],
                    [
                      <strong>Parallel research</strong>,
                      <span className="small muted">
                        Source retrieval and extraction
                      </span>,
                      paidProviders.includes("parallel") ? (
                        <Badge tone="is-success">Enabled</Badge>
                      ) : (
                        <Badge tone="is-warning">Disabled by default</Badge>
                      ),
                    ],
                    [
                      <strong>Storage</strong>,
                      <span className="small muted">Scripts and exports</span>,
                      <span className="mono small">{deployment.storageAdapter}</span>,
                    ],
                    [
                      <strong>Identity</strong>,
                      <span className="small muted">Sign-in and sessions</span>,
                      <span className="mono small">
                        {deployment.authenticationAdapter}
                      </span>,
                    ],
                    [
                      <strong>Background work</strong>,
                      <span className="small muted">
                        Detection, research and rescan jobs
                      </span>,
                      deployment.dispatchEnabled ? (
                        <span className="mono small">{deployment.dispatchAdapter}</span>
                      ) : (
                        <Badge tone="is-warning">Dispatch disabled</Badge>
                      ),
                    ],
                  ]}
                />
                <div className="gap-t-5">
                  <Banner
                    icon="ℹ"
                    title="Paid providers are off until they are acknowledged"
                    message="Gemini and Parallel default to disabled. Enabling either takes an explicit cost acknowledgement and a bounded concurrency limit, so no paid call happens by accident. Retry history for a provider call lives in Records, not here."
                  />
                </div>
              </>
            )}
          </Section>
        )}

        {/* ── Data & privacy ───────────────────────────────────────────── */}
        {tab === "data" && (
          <Section
            title="Data & privacy"
            description="What ClearCut stores, and the only way it leaves."
          >
            <DataTable
              caption="Stored data classes"
              columns={[
                { label: "What is stored" },
                { label: "Retention" },
                { label: "Removed by" },
              ]}
              rows={[
                [
                  <strong>Original scripts and parsed structure</strong>,
                  <span className="small">Kept indefinitely</span>,
                  <span className="small">Project deletion</span>,
                ],
                [
                  <strong>Source snapshots and evidence</strong>,
                  <span className="small">Kept indefinitely</span>,
                  <span className="small">Project deletion</span>,
                ],
                [
                  <strong>Decisions and audit events</strong>,
                  <span className="small">Kept indefinitely</span>,
                  <Badge tone="is-warning">Never selectively</Badge>,
                ],
                [
                  <strong>Reports and export artifacts</strong>,
                  <span className="small">Kept indefinitely</span>,
                  <span className="small">Project deletion</span>,
                ],
                [
                  <strong>Operational logs and provider payloads</strong>,
                  <span className="small">Bounded telemetry window</span>,
                  <span className="small">Automatic</span>,
                ],
              ]}
            />
            <div className="gap-t-5">
              <Banner
                tone="is-accent"
                icon="ℹ"
                title="Private scripts are never used for shared-model training"
                message="Signed download links are short-lived and regenerated on demand. A link expiring does not delete the artifact."
              />
            </div>
            <div className="gap-t-5">
              <Card
                eyebrow="Deletion"
                title="Only an Owner can delete a project or organization"
              >
                <p className="small">
                  Individual claims, snapshots, decisions and audit events cannot be
                  deleted on their own — removing one link would make the remaining
                  record misleading. Deletion takes the whole project or the whole
                  organization.
                </p>
                <ul className="stack-sm gap-t-3">
                  <li className="small">
                    Scheduling makes the resource read-only, blocks new jobs and
                    governed actions, and revokes signed links.
                  </li>
                  <li className="small">
                    A grace period follows, during which an Owner can restore it.
                  </li>
                  <li className="small">
                    Final purge removes sensitive content and blobs, keeping only the
                    minimum tombstone the audit boundary needs.
                  </li>
                  <li className="small">
                    Any report whose source material was purged becomes explicitly
                    unavailable rather than claiming it is still reproducible.
                  </li>
                </ul>
                <p className="small muted gap-t-3">
                  Scheduling a deletion is not offered from this surface: it is a
                  governed action against a specific project or organization, and it
                  is triggered where that target is in scope.
                </p>
              </Card>
            </div>
          </Section>
        )}

        {/* ── Governance ───────────────────────────────────────────────── */}
        {tab === "governance" && (
          <>
            <Section
              title="Organization policy"
              description="Owner-governed and versioned. An active version is immutable: changing one supersedes it and writes an audit event in the same transaction. Admin may inspect; only an Owner may validate or activate."
            >
              {configurationsQuery.isPending ? (
                <p role="status" className="small muted">
                  Loading protected configuration…
                </p>
              ) : configurationsQuery.isError ? (
                <Banner
                  tone="is-danger"
                  icon="⚠"
                  title="Could not read the protected configuration"
                  message={`${errorMessage(configurationsQuery.error)} No policy version has been inferred as active.`}
                  role="alert"
                />
              ) : (
                <>
                  {configurationError && (
                    <div className="gap-b-4">
                      <Banner
                        tone="is-danger"
                        icon="⚠"
                        title="The lifecycle did not change"
                        message={configurationError}
                        role="alert"
                        titleIsHeading
                      />
                    </div>
                  )}
                  {validateConfiguration.isSuccess &&
                    !validateConfiguration.data.valid && (
                      <div className="gap-b-4">
                        <Banner
                          tone="is-warning"
                          icon="⚠"
                          title="Validation found issues"
                          message={
                            validateConfiguration.data.issues?.join(" ") ??
                            "The draft was not accepted for activation."
                          }
                          role="status"
                          titleIsHeading
                        />
                      </div>
                    )}
                  <ProtectedConfigurationTable
                    configurations={configurationsQuery.data ?? []}
                    canGovern={canGovern}
                    pendingConfigurationId={configurationPendingId}
                    onValidate={(configurationId) => {
                      activateConfiguration.reset();
                      validateConfiguration.mutate(configurationId);
                    }}
                    onActivate={(configurationId) => {
                      validateConfiguration.reset();
                      activateConfiguration.mutate(configurationId);
                    }}
                  />
                </>
              )}

              <div className="gap-t-5">
                <ProtectedRulesBanner />
              </div>
            </Section>

            {canGovern && (
              <Section title="Raise a new version">
                <DraftConfigurationForm
                  saving={draftConfiguration.isPending}
                  error={errorMessage(draftConfiguration.error)}
                  drafted={draftConfiguration.isSuccess}
                  onDraft={(input) => draftConfiguration.mutate(input)}
                />
              </Section>
            )}

            <Section
              title="Data handling"
              description="Evidence is kept until the project is deleted, as set out under Data & privacy. These rules govern everything else."
            >
              <Card>
                <div className="stack">
                  <div className="toggle-row">
                    <div>
                      <strong className="small">Script content in training</strong>
                      <p className="field-hint">
                        Private scripts are never used to train shared models.
                      </p>
                    </div>
                    <Badge tone="is-success">Never</Badge>
                  </div>
                  <div className="toggle-row">
                    <div>
                      <strong className="small">Export links</strong>
                      <p className="field-hint">
                        Signed download links are short-lived and regenerated on
                        demand.
                      </p>
                    </div>
                    <Badge>Short-lived</Badge>
                  </div>
                </div>
              </Card>
            </Section>
          </>
        )}
      </div>
    </Page>
  );
}

export default SettingsRoute;

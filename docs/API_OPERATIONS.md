# ClearCut API Operation Inventory

**Status:** implementation contract inventory  
**OpenAPI source:** `packages/contracts/openapi.yaml`

This inventory freezes semantic operation ownership before route or UI implementation. OpenAPI may add read projections and support operations, but it must not rename these intents or replace governed commands with generic CRUD.

## Conventions

- Prefix: `/api/v1`.
- Organization paths use `/organizations/{orgId}`.
- Project-owned paths continue with `/projects/{projectId}`.
- All project operations derive the actor from the opaque session and re-check current membership/project access.
- Retryable commands require `Idempotency-Key`.
- Governed commands also require rationale, expected version, intent hash, and any required attestation.
- Unknown and unauthorized resource IDs return the same safe not-found response class.
- Long-running commands return `202` with a typed job resource.
- All operation IDs remain stable across generated clients.

## Identity and tenancy

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `createSession` | `POST /sessions` | operational | 02a |
| `deleteCurrentSession` | `DELETE /sessions/current` | operational | 02a |
| `getSessionContext` | `GET /session-context` | read | 02a |
| `requestPasswordRecovery` | `POST /password-recovery-requests` | operational | 02a |
| `completePasswordRecovery` | `POST /password-recovery-completions` | operational | 02a |
| `resolveOrganizationEntry` | `GET /organization-entry` | read | 02b |
| `createOrganization` | `POST /organizations` | governed bootstrap | 02b |
| `listOrganizations` | `GET /organizations` | read | 02b |
| `listProjects` | `GET /organizations/{orgId}/projects` | read | 02b |
| `createProject` | `POST /organizations/{orgId}/projects` | operational | 02b |
| `createInvitation` | `POST /organizations/{orgId}/invitations` | operational or governed by role/policy | 02c |
| `resendInvitation` | `POST /organizations/{orgId}/invitations/{invitationId}:resend` | operational | 02c |
| `revokeInvitation` | `POST /organizations/{orgId}/invitations/{invitationId}:revoke` | operational | 02c |
| `acceptInvitation` | `POST /invitations/{token}:accept` | operational | 02c |
| `declineInvitation` | `POST /invitations/{token}:decline` | operational | 02c |
| `changeMembershipRole` | `POST /organizations/{orgId}/memberships/{membershipId}:changeRole` | governed | 02c |
| `changeProjectGrant` | `POST /organizations/{orgId}/memberships/{membershipId}:changeProjectGrant` | governed | 02c |
| `deactivateMembership` | `POST /organizations/{orgId}/memberships/{membershipId}:deactivate` | governed | 02c |
| `reactivateMembership` | `POST /organizations/{orgId}/memberships/{membershipId}:reactivate` | governed | 02c |

## Scripts and analysis

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `createUploadCapability` | `POST /organizations/{orgId}/projects/{projectId}/upload-capabilities` | operational | 03a |
| `finalizeImportArtifact` | `POST /organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:finalize` | operational | 03a |
| `createPasteImport` | `POST /organizations/{orgId}/projects/{projectId}/paste-imports` | operational | 03b |
| `parseImportArtifact` | `POST /organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:parse` | operational async | 03b |
| `acceptParseWarnings` | `POST /organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:acceptWarnings` | governed | 03b |
| `commitScriptVersion` | `POST /organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:commitVersion` | governed | 03b |
| `startDetection` | `POST /organizations/{orgId}/projects/{projectId}/script-versions/{versionId}:detect` | operational async | 04a |
| `startResearch` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:research` | operational async | 05a |
| `retryJob` | `POST /organizations/{orgId}/projects/{projectId}/jobs/{jobId}:retry` | operational | 04a |
| `cancelJob` | `POST /organizations/{orgId}/projects/{projectId}/jobs/{jobId}:cancel` | operational | 04a |
| `getJob` | `GET /organizations/{orgId}/projects/{projectId}/jobs/{jobId}` | read | 04a |
| `getClearanceItemEvidence` | `GET /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/evidence` | read | 05c |

## Review and collaboration

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `assignClearanceItem` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:assign` | operational | 07b |
| `changeClearanceItemDueDate` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:changeDueDate` | operational | 07b |
| `recordEvidenceDecision` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:recordEvidenceDecision` | governed | 07b |
| `setDisposition` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:setDisposition` | governed | 07b |
| `referClearanceItem` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:refer` | governed | 07b |
| `acknowledgeReferral` | `POST /organizations/{orgId}/projects/{projectId}/referrals/{referralId}:acknowledge` | governed | 07b |
| `addComment` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments` | operational | 07c |
| `replyToComment` | `POST /organizations/{orgId}/projects/{projectId}/comments/{commentId}:reply` | operational | 07c |
| `reviseComment` | `POST /organizations/{orgId}/projects/{projectId}/comments/{commentId}:revise` | operational | 07c |
| `proposeRewrite` | `POST /organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:proposeRewrite` | draft | 08a |
| `approveRewrite` | `POST /organizations/{orgId}/projects/{projectId}/rewrite-proposals/{proposalId}:approve` | governed | 08a |
| `rejectRewrite` | `POST /organizations/{orgId}/projects/{projectId}/rewrite-proposals/{proposalId}:reject` | governed | 08a |
| `withdrawRewrite` | `POST /organizations/{orgId}/projects/{projectId}/rewrite-proposals/{proposalId}:withdraw` | draft | 08a |
| `startSelectiveRescan` | `POST /organizations/{orgId}/projects/{projectId}/script-versions/{versionId}:startSelectiveRescan` | operational async, created by approval transaction where applicable | 08b |

## Monitoring, notifications, trust, and records

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `changeMonitoringCadence` | `POST /organizations/{orgId}/projects/{projectId}/monitoring-policy:changeCadence` | operational | 09a |
| `startMonitoringRun` | `POST /organizations/{orgId}/projects/{projectId}/monitoring-runs` | operational async | 09a |
| `reviewMonitoringChange` | `POST /organizations/{orgId}/projects/{projectId}/monitoring-reviews/{reviewId}:recordDecision` | governed | 09b |
| `listNotifications` | `GET /organizations/{orgId}/notifications` | read | 09c |
| `markNotificationRead` | `POST /organizations/{orgId}/notifications/{notificationId}:markRead` | operational | 09c |
| `markAllNotificationsRead` | `POST /organizations/{orgId}/notifications:markAllRead` | operational | 09c |
| `registerPushSubscription` | `POST /push-subscriptions` | operational | 09c |
| `revokePushSubscription` | `DELETE /push-subscriptions/{subscriptionId}` | operational | 09c |
| `listRecords` | `GET /organizations/{orgId}/records` | read | 10a |
| `getRecord` | `GET /organizations/{orgId}/records/{recordId}` | read | 10a |
| `validateProtectedConfiguration` | `POST /organizations/{orgId}/protected-configurations/{configurationId}:validate` | operational | 10b |
| `activateProtectedConfiguration` | `POST /organizations/{orgId}/protected-configurations/{configurationId}:activate` | governed Owner-only | 10b |
| `promoteLearningCandidate` | `POST /organizations/{orgId}/learning-candidates/{candidateId}:promote` | governed Owner-only | 10b |
| `rollbackLearningCandidate` | `POST /organizations/{orgId}/learning-candidates/{candidateId}:rollback` | governed Owner-only or automatic gate | 10b |
| `scheduleDeletion` | `POST /organizations/{orgId}/deletion-requests` | governed Owner-only | 10c |
| `restoreDeletion` | `POST /organizations/{orgId}/deletion-requests/{requestId}:restore` | governed Owner-only | 10c |

Provider ingress is not a user operation and never derives tenant scope from payload metadata:

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `receiveParallelMonitorWebhook` | `POST /webhooks/parallel/monitor` | signed provider ingress; conditional | 09a |

`receiveParallelMonitorWebhook` verifies the exact-body Parallel HMAC signature, timestamp tolerance, and replay ID before JSON parsing; it then resolves scope only through the persisted local `monitor_id`/opaque correlation mapping.

## Reports

| Operation ID | Method and path | Class | Owner |
|---|---|---|---|
| `previewReport` | `GET /organizations/{orgId}/projects/{projectId}/report-preview` | read/draft projection | 11a |
| `generateReportSnapshot` | `POST /organizations/{orgId}/projects/{projectId}/report-snapshots` | governed async | 11a |
| `getReportSnapshot` | `GET /organizations/{orgId}/projects/{projectId}/report-snapshots/{snapshotId}` | read | 11a |
| `releaseReport` | `POST /organizations/{orgId}/projects/{projectId}/report-snapshots/{snapshotId}:release` | governed | 11b |
| `downloadReleasedReport` | `GET /organizations/{orgId}/projects/{projectId}/report-releases/{releaseId}/artifact` | read | 11b |

Downloading an already released artifact is an authorized read, not a new governed export decision. Generation and initial release are the governed boundaries.

## Contract acceptance

For every operation, the OpenAPI implementation plan must add:

1. explicit request and response schemas;
2. security requirements and ownership class;
3. stable `operationId`;
4. declared success and error statuses;
5. idempotency and concurrency behavior;
6. examples for success, authorization-safe not-found, validation, conflict, and typed provider failure where applicable;
7. generated TypeScript and Python client tests;
8. an API-only golden-path test proving the feature does not depend on UI logic.

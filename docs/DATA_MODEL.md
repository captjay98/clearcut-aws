# ClearCut Data Model

**Status:** logical model; physical schema freezes incrementally through contracts and migrations

## Ownership rule

- Account-owned: `User`, credentials/provider identity, sessions, account security events.
- Organization-owned: organizations, memberships, invitations, organization policy/prompt/rubric/preference/privacy/retention versions, learning candidates, organization notifications.
- Project-owned: projects, script/evidence/workflow records, project notifications, reports.
- Explicit global catalogs only: fixed roles/capabilities, ten protected clearance categories, platform source-authority defaults.

Every project record carries `org_id` and `project_id`; foreign keys and repository APIs make the pair unavoidable.

## Core aggregates

### Identity and tenancy

`User`, `LocalCredential` or `ProviderIdentity`, `Session`, `Organization`, `Membership`, `Invitation`, `Project`, `ProjectMembership`, `SecurityEvent`.

Invitation states:

```text
pending -> accepted | declined | expired | revoked
```

Tokens are versioned, single-use, high entropy, stored only as hashes. Edit/resend invalidates the prior token. Acceptance is idempotent and email-bound.

### Script ingestion and versions

`ImportArtifact`, `ParseRun`, `Script`, `ScriptVersion`, `ScriptElement`, `ElementSpan`, `VersionLineage`, `VersionDiff`.

Every import/approved rewrite creates an immutable version. Elements/spans use stable logical IDs plus version-specific positions. Source bytes and normalized structure are separately hashed.

### Detection and evidence

`AnalysisRun`, `DetectionRun`, `ClearanceItem`, `ItemVersionState`, `ResearchRun`, `ResearchQuery`, `ProviderAttempt`, `SourceSnapshot`, `EvidenceClaim`, `EvidenceConflict`, `ConfidenceAssessment`.

`ClearanceItem` has stable logical identity; state is not one overloaded status. At minimum preserve independent Search execution, Extract enrichment, evidence-assessment, workflow, remediation, and disposition dimensions.

`ProviderAttempt.operation` distinguishes `search`, `extract`, and conditional Monitor lifecycle/event operations. Search and Extract attempts under one `ResearchRun` share a ClearCut-generated non-semantic session key and retain provider `search_id`, `extract_id`, and `session_id` where supplied. `SourceSnapshot.excerpt_origin` is `search_excerpt` or `extract_excerpt`; an Extract snapshot also binds to its authorizing Search result from the same project/run.

```python
class EvidenceClaim(BaseModel):
    item_id: UUID
    script_version_id: UUID
    source_snapshot_id: UUID
    research_query_id: UUID
    attributable_excerpt: str
    stance: Literal["supports", "disagrees", "context"]
    confidence: Decimal
```

Database constraints prevent an `EvidenceClaim` without the cited source/query/version relationships. An item with no claims remains valid and unresolved.

### Human workflow

`Assignment`, `Comment`, `CommentRevision`, `Mention`, `EvidenceDecision`, `SpecialistReferral`, `RewriteProposal`, `DispositionDecision`, `FollowUpTask`, `MonitoringReview`.

Decisions are append-only/superseding. Current state is a projection; reversing or reopening never deletes history.

### Durable operations and trust

`Job`, `JobAttempt`, `OutboxMessage`, `InboxReceipt`, `AgentRun`, `AgentToolCall`, `DeterministicGateResult`, `JudgeVerdict`, `AgentEvaluation`, `LearningProposal`, `LearningCandidate`, `CanaryRun`, `PromptVersion`, `PolicyVersion`, `RubricVersion`.

### Delivery and record

`MonitoringPolicy`, `EvidenceWatch`, `MonitoringRun`, `ProviderMonitor`, `ProviderWebhookReceipt`, `ProviderMonitorEvent`, `SourceChange`, `ReviewItem`, `ReportSnapshot`, `ReportRelease`, `ExportArtifact`, `AuditEvent`, `ReceiptProjection`, `Notification`, `NotificationDeliveryAttempt`, `PushSubscription`, `DeletionRequest`, `DeletionTombstone`.

Conditional Monitor records use opaque local-to-provider correlation. Provider metadata never stores or establishes tenant authorization. A `ProviderMonitorEvent` is untrusted input and must link to a later verification `ResearchRun`; it cannot be cited directly by an `EvidenceClaim`.

`AuditEvent` is authoritative. Receipt is rebuildable, redacted display data. `ReportSnapshot` is immutable generation output; `ReportRelease` is the human attestation referencing it.

## Common fields

Every ClearCut-owned aggregate uses UUIDv7 IDs, `created_at`, `updated_at` where mutable, optimistic `version`, and scoped actor/correlation metadata. External provider IDs remain opaque length-bounded strings. All timestamps are UTC at rest and rendered in the user's locale. Monetary/provider-cost fields use decimal minor units, never float.

## Deletion

Core evidence has no age-based deletion. An Owner may schedule a whole project or organization for deletion with a 30-day reversible grace period. During grace, it is read-only and links/jobs are revoked. Purge deletes sensitive bodies/blobs, retains minimum tombstone/audit linkage, and marks lost reproducibility explicitly.

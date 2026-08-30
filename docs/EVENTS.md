# ClearCut Events and Delivery

## Event envelope

```json
{
  "eventId": "uuid",
  "eventType": "clearance-item.assigned.v1",
  "occurredAt": "2026-08-30T00:00:00Z",
  "orgId": "uuid",
  "projectId": "uuid-or-null",
  "actor": {"type": "user", "id": "uuid"},
  "aggregate": {"type": "clearanceItem", "id": "uuid", "version": 4},
  "correlationId": "uuid",
  "causationId": "uuid-or-null",
  "payload": {}
}
```

Schemas are versioned in `packages/contracts/schemas/events/`. Consumers reject unknown incompatible versions visibly; they do not guess fields.

## Transactional delivery

The originating transaction writes domain state, authoritative `AuditEvent` when required, and outbox messages together. A dispatcher leases rows, publishes idempotently, records attempts, and reconciles stranded work. Consumers use an inbox/event ID to make duplicate delivery harmless.

Signed Parallel Monitor webhooks are provider ingress, not ClearCut domain events. After exact-body signature/timestamp/replay verification, the receiver stores a bounded immutable receipt and emits an internal operational outbox message. The worker resolves organization/project scope from the persisted local monitor mapping, fetches the provider event group, and starts Search/Extract verification. Only subsequent verified ClearCut state may emit a domain/notification event.

## Event classes

- **Domain:** authoritative fact such as invitation accepted, version committed, item assigned, evidence decision recorded, rewrite approved, report released.
- **Operational:** job attempt, provider result, email delivery, retry, reconciliation, security signal.
- **Notification projection:** redacted recipient-specific message derived from a domain/operational event.
- **AuditEvent:** immutable authoritative record of a consequential action; not a generic event-stream copy.

## Notification taxonomy

Tiers are urgent, action-required, and informational. Recipients are computed from event type, assignment/ownership, fixed role, and current project authorization. The actor is excluded. Payloads contain no screenplay text, source excerpt, prompt/model/rubric identifiers, provider receipt, token, or credential.

Destinations are structured:

```json
{"orgId":"...","projectId":"...","entityType":"clearanceItem","entityId":"..."}
```

The UI resolves them after authorization. Deleted or unauthorized targets show a safe unavailable explanation; they never fall back to another item.

## Delivery layers

- SSE for in-app real-time updates.
- Polling as universal fallback and unread-count source.
- Web Push for urgent events only after explicit permission.

Delivery attempts belong in Records/Operations, not the inbox.

## Evolution rules

Additive compatible fields stay in the event version. Semantic/removal/type changes create a new version and dual-read migration. Event retention never becomes the only copy of evidence provenance or governed audit.

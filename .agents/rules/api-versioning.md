---
trigger: file_change
globs: ['**/openapi.yaml', '**/openapi.yml', '**/contracts/**', '**/routes/**', '**/router*.py', '**/router*.ts']
---

# API Versioning and Scope

API changes start with the contract, not the implementation. ClearCut's OpenAPI contract is the source of truth for the planned FastAPI API and generated TypeScript/Python clients.

## Contract Flow

1. Edit `packages/contracts/openapi.yaml` when that planned path exists.
2. Regenerate clients with the repository's pinned contract command.
3. Implement the FastAPI route/service and update the TanStack/Astro consumer.
4. Verify generated-client drift and representative approval, failure, and recovery paths.

Do not claim these commands have run while the target directories/toolchain are absent.

## Versioning Rules

- All endpoints are prefixed `/api/v1/`; no unversioned routes.
- Breaking changes require a new version or migration period.
- Additive optional fields and endpoints are safe within the current version.
- Route handlers use Pydantic request/response models and explicit operation IDs.
- No raw dicts cross module boundaries or serve as an undocumented response contract.

## Ownership-Aware Tenant Scoping

Scope is determined by resource ownership, not by a blanket rule:

- Organization-owned resources (organization, membership, invitation, organization settings) accept `org_id` from authenticated context; never trust a client-supplied organization ID.
- Project-owned resources (scripts, versions, elements, clearance items, evidence, research, decisions, assignments, comments, monitoring, exports) take `project_id` from the URL and enforce both authenticated `org_id` and project membership/ownership.
- Explicitly global resources are limited to role/capability definitions, the ten category schema, and platform source-authority defaults; they contain no user data and cannot bypass authorization. Organization policy, prompt, preference, retention, and privacy configurations and versions remain `org_id`-scoped.

```python
# ✅ CORRECT — project-owned resource
@router.get('/api/v1/projects/{project_id}/clearance-items')
async def list_items(project_id: str, actor: Actor = Depends(get_actor)):
    await project_access.require(actor=actor, project_id=project_id)
    return await item_service.list(org_id=actor.org_id, project_id=project_id)

# ✅ CORRECT — organization-owned resource
@router.get('/api/v1/organizations/me/memberships')
async def list_memberships(actor: Actor = Depends(get_actor)):
    return await membership_service.list(org_id=actor.org_id)

# ❌ WRONG — unscoped project data
@router.get('/api/v1/clearance-items')
async def list_items():
    return await item_service.list_all()
```

## Evidence Contract

A detection response may contain a project-owned `ClearanceItem` with zero claims and an explicit pending/no-result/unavailable/failed state. An `EvidenceClaim` response is invalid unless it references a Parallel `SourceSnapshot` with URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/run identity, and provenance. The category schema and source-authority policy are separate protected contracts.

## Verification

When implementation exists, run the pinned contract-generation/drift check, backend and frontend type checks, and relevant tests. For the current pre-implementation repository, validate source guidance and regenerate canonical agent output unless the active delegation explicitly reserves generation.

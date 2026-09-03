import {
  createApiClient,
  type CreateSessionRequest,
  type Project,
  type ResponseMeta,
  type SessionContext,
} from '../../../packages/contracts/generated/typescript/index'

const api = createApiClient({ baseUrl: 'http://localhost:8000' })
const orgId = '01900000-0000-7000-8000-000000000001'
const projectId = '01900000-0000-7000-8000-000000000002'
const jobId = '01900000-0000-7000-8000-000000000003'
const snapshotId = '01900000-0000-7000-8000-000000000004'

function consume(_value: unknown): void {}

const loggedOutSession: SessionContext = {
  authenticated: false,
  userId: null,
  email: null,
  activeOrgId: null,
  role: null,
}
const projectWithoutDescription: Project = {
  projectId,
  orgId,
  title: 'Untitled project',
  description: null,
  productionType: null,
  productionStage: null,
  jurisdiction: null,
  targetLockDate: null,
  reviewBrief: null,
  createdAt: '2026-09-02T00:00:00Z',
}
const credentials: CreateSessionRequest = {
  email: 'contract@example.com',
  password: 'Password123!',
}
consume(loggedOutSession)
consume(projectWithoutDescription)
consume(credentials)

// @ts-expect-error Session creation requires a password.
const missingPassword: CreateSessionRequest = { email: 'contract@example.com' }
consume(missingPassword)

async function verifyGeneratedClientContract(): Promise<void> {
  const organizationEntry = await api.resolveOrganizationEntry()
  if (organizationEntry.ok) {
    const defaultOrgSlug: string | null | undefined = organizationEntry.value.defaultOrgSlug
    const defaultOrgId: string | null | undefined = organizationEntry.value.defaultOrgId
    consume(defaultOrgSlug)
    consume(defaultOrgId)
  }

  const job = await api.getJob({ params: { orgId, projectId, jobId } })
  if (job.ok) {
    consume(job.value)
    const firstLifecycleAction: 'cancelled' | 'retry_requested' | undefined =
      job.value.history[0]?.action
    consume(firstLifecycleAction)
    const meta: ResponseMeta | undefined = job.meta
    consume(meta)
  }

  await api.listRecords({
    params: { orgId },
    query: { view: 'runsAndTools', projectId },
  })

  await api.createProject({
    params: { orgId },
    body: { title: 'Fixture project' },
  })

  await api.registerUser({
    body: {
      name: 'Contract Tester',
      email: 'contract@example.com',
      password: 'Password123!',
    },
  })

  await api.createUploadCapability({
    params: { orgId, projectId },
    body: { filename: 'screenplay.fountain', contentType: 'text/plain' },
  })

  await api.finalizeImportArtifact({
    params: { orgId, projectId, artifactId: snapshotId },
    body: { file: new Blob(['Title: Signal Fires'], { type: 'text/plain' }) },
    headers: { 'X-Upload-Nonce': 'nonce' },
  })

  // @ts-expect-error Multipart finalize requires the accountable upload nonce header.
  await api.finalizeImportArtifact({
    params: { orgId, projectId, artifactId: snapshotId },
    body: { file: new Blob(['screenplay']) },
  })

  await api.generateReportSnapshot({
    params: { orgId, projectId },
    body: {},
  })

  await api.releaseReport({
    params: { orgId, projectId, snapshotId },
    body: { attestation: 'Reviewed by an accountable human.' },
  })

  // @ts-expect-error Registration requires a human-readable name.
  await api.registerUser({ body: { email: 'contract@example.com', password: 'Password123!' } })

  await api.createUploadCapability({
    params: { orgId, projectId },
    // @ts-expect-error Upload capabilities accept contentType, not the obsolete mimeType field.
    body: { filename: 'screenplay.fountain', mimeType: 'text/plain' },
  })

  // @ts-expect-error Canonical path variables are supplied through params.
  await api.getJob({ path: { orgId, projectId, jobId } })

  // @ts-expect-error Canonical generated parameter names are camelCase.
  await api.getJob({ params: { org_id: orgId, projectId, jobId } })

  // @ts-expect-error Governed generation requires an explicit request body.
  await api.generateReportSnapshot({ params: { orgId, projectId } })

  // @ts-expect-error Governed release requires the accountable-human attestation body.
  await api.releaseReport({ params: { orgId, projectId, snapshotId } })

  // @ts-expect-error Records views use the protected five-value vocabulary.
  await api.listRecords({ params: { orgId }, query: { view: 'everything' } })

  if (job.ok) {
    // @ts-expect-error Successful payloads are already unwrapped.
    consume(job.value.data)
  }
}

void verifyGeneratedClientContract()

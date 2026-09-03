import {
  createApiClient,
  type ApiError,
  type ApiResult,
} from '../../../packages/contracts/generated/typescript/index'

const api = createApiClient({ baseUrl: 'http://localhost:8000' })
const orgId = '01900000-0000-7000-8000-000000000001'
const projectId = '01900000-0000-7000-8000-000000000002'
const itemId = '01900000-0000-7000-8000-000000000003'
const referralId = '01900000-0000-7000-8000-000000000004'
const commentId = '01900000-0000-7000-8000-000000000005'
const assigneeId = '01900000-0000-7000-8000-000000000006'
const headers = { 'Idempotency-Key': 'task-10-key-0001' }
const versioned = { expectedVersion: 7, intentHash: 'sha256:task-10-intent' }

function consumeTypedError(error: ApiError): void {
  const code: ApiError['code'] = error.code
  const requestId: string = error.requestId
  const retryable: boolean = error.retryable
  void code
  void requestId
  void retryable
}

// Narrow a success result that carries a resulting ClearanceItem.version.
function consumeItemVersion(result: ApiResult<{ version: number }>): void {
  if (result.ok) {
    const version: number = result.value.version
    void version
  } else {
    consumeTypedError(result.error)
  }
}

// Narrow a success result that carries a resulting itemVersion projection.
function consumeReferralItemVersion(result: ApiResult<{ itemVersion: number }>): void {
  if (result.ok) {
    const itemVersion: number = result.value.itemVersion
    void itemVersion
  } else {
    consumeTypedError(result.error)
  }
}

async function verifyTask10GeneratedClient(): Promise<void> {
  const decisionResult = await api.recordEvidenceDecision({
    params: { orgId, projectId, itemId },
    headers,
    body: {
      decision: 'further_review_required',
      rationale: 'The cited evidence remains inconclusive.',
      ...versioned,
    },
  })
  if (decisionResult.ok) {
    const itemVersion: number = decisionResult.value.version
    void itemVersion
  } else {
    consumeTypedError(decisionResult.error)
  }
  const dispositionResult = await api.setDisposition({
    params: { orgId, projectId, itemId },
    headers,
    body: {
      disposition: 'deferred',
      rationale: 'A qualified human must review the unresolved evidence.',
      ...versioned,
    },
  })
  consumeItemVersion(dispositionResult)
  const referralResult = await api.referClearanceItem({
    params: { orgId, projectId, itemId },
    headers,
    body: {
      targetRole: 'reviewer',
      question: 'Please assess the conflicting cited sources.',
      rationale: 'Specialist review is required before disposition.',
      ...versioned,
    },
  })
  if (referralResult.ok) {
    const itemVersion: number = referralResult.value.itemVersion
    void itemVersion
  } else {
    consumeTypedError(referralResult.error)
  }
  const acknowledgeResult = await api.acknowledgeReferral({
    params: { orgId, projectId, itemId, referralId },
    headers,
    body: {
      response: 'Acknowledged for evidence review.',
      rationale: 'I accept responsibility for the requested review.',
      ...versioned,
    },
  })
  consumeReferralItemVersion(acknowledgeResult)
  const assignResult = await api.assignClearanceItem({
    params: { orgId, projectId, itemId },
    headers,
    body: { assigneeId, ...versioned },
  })
  consumeItemVersion(assignResult)
  const commentResult = await api.addComment({
    params: { orgId, projectId, itemId },
    headers,
    body: { body: 'Please compare the cited source dates.', mentions: [assigneeId], ...versioned },
  })
  if (commentResult.ok) {
    const itemVersion: number = commentResult.value.itemVersion
    void itemVersion
  } else {
    consumeTypedError(commentResult.error)
  }
  const replyResult = await api.replyToComment({
    params: { orgId, projectId, itemId, commentId },
    headers,
    body: { body: 'The source dates have been compared.', mentions: [], ...versioned },
  })
  consumeReferralItemVersion(replyResult)
  const reviseResult = await api.reviseComment({
    params: { orgId, projectId, itemId, commentId },
    headers,
    body: { body: 'The cited source dates have been compared.', mentions: [], ...versioned },
  })
  consumeReferralItemVersion(reviseResult)

  // @ts-expect-error Versioned commands require Idempotency-Key.
  await api.assignClearanceItem({
    params: { orgId, projectId, itemId },
    body: { assigneeId, ...versioned },
  })

  await api.recordEvidenceDecision({
    params: { orgId, projectId, itemId },
    headers,
    // @ts-expect-error Governed commands require rationale, expectedVersion, and intentHash.
    body: { decision: 'accepted' },
  })
}

void verifyTask10GeneratedClient()

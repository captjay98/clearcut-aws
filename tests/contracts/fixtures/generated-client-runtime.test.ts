import { describe, expect, it, vi } from 'vitest'

import { createApiClient } from '../../../packages/contracts/generated/typescript/index'

const protocolFailure = {
  ok: false,
  error: {
    code: 'internal_error',
    message: 'Successful response did not contain valid JSON',
    requestId: 'protocol-response',
    retryable: false,
  },
}

function clientReturning(response: Response) {
  const fetchMock = vi.fn<typeof fetch>(async () => response)
  return {
    api: createApiClient({ baseUrl: 'http://localhost:8000', fetch: fetchMock }),
    fetchMock,
  }
}

describe('generated client response protocol', () => {
  it.each([
    ['empty', new Response(null, { status: 200, headers: { 'x-request-id': 'protocol-response' } })],
    [
      'malformed JSON',
      new Response('{', {
        status: 200,
        headers: { 'content-type': 'application/json', 'x-request-id': 'protocol-response' },
      }),
    ],
    [
      'non-JSON',
      new Response('plain text', {
        status: 200,
        headers: { 'content-type': 'text/plain', 'x-request-id': 'protocol-response' },
      }),
    ],
  ])('returns a typed failure for a successful %s response', async (_caseName, response) => {
    const { api } = clientReturning(response)

    await expect(api.resolveOrganizationEntry()).resolves.toEqual(protocolFailure)
  })

  it('preserves explicit 204 success handling', async () => {
    const { api } = clientReturning(new Response(null, { status: 204 }))

    await expect(api.resolveOrganizationEntry()).resolves.toEqual({ ok: true, value: undefined })
  })

  it('preserves typed API error envelopes', async () => {
    const error = {
      code: 'conflict_stale_version' as const,
      message: 'The item version changed.',
      requestId: 'typed-error',
      retryable: false,
    }
    const { api } = clientReturning(
      new Response(JSON.stringify({ error }), {
        status: 409,
        headers: { 'content-type': 'application/json' },
      }),
    )

    await expect(api.resolveOrganizationEntry()).resolves.toEqual({ ok: false, error })
  })
})

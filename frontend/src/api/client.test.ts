import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, UNAUTHORIZED_EVENT, describeError, request, tokenStore } from './client'

/** Awaits a promise that must reject and returns the error. */
async function fail(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p
  } catch (e) {
    return e as ApiError
  }
  throw new Error('expected the request to fail')
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })

beforeEach(() => {
  localStorage.clear()
})
afterEach(() => vi.restoreAllMocks())

describe('request error mapping', () => {
  it('turns a network failure into a friendly, retryable error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const e = await fail(request('/x'))
    expect(e).toBeInstanceOf(ApiError)
    expect(e.kind).toBe('network')
    expect(e.retryable).toBe(true)
    expect(e.message).toMatch(/reach the server|offline/i)
  })

  it('times out slow requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_u, init) =>
        new Promise((_res, rej) => init?.signal?.addEventListener('abort', () => rej(new DOMException('x', 'AbortError')))),
    )
    const e = await fail(request('/x', {}, { timeoutMs: 20 }))
    expect(e.kind).toBe('timeout')
  })

  it('a 401 on a normal call clears the token and announces the expired session', async () => {
    tokenStore.set('t')
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { detail: 'Not authenticated' }))
    const e = await fail(request('/documents'))
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
    expect(e.kind).toBe('unauthorized')
    expect(e.message).toMatch(/session has expired/i)
    expect(tokenStore.get()).toBeNull()
    expect(spy).toHaveBeenCalledOnce()
  })

  it('a 401 from login is a wrong-password message, not a session expiry', async () => {
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { detail: 'Invalid email or password' }))
    const e = await fail(request('/auth/login', { method: 'POST', body: '{}' }, { isAuthRequest: true }))
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
    expect(e.message).toBe('Invalid email or password')
    expect(spy).not.toHaveBeenCalled()
  })

  it('formats FastAPI validation errors readably', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(422, { detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address' }] }),
    )
    const e = await fail(request('/auth/register', { method: 'POST', body: '{}' }))
    expect(e.message).toBe('email: value is not a valid email address')
  })

  it('explains rate limiting with the wait time', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(429, { detail: 'x' }, { 'retry-after': '12' }))
    const e = await fail(request('/x'))
    expect(e.kind).toBe('rate_limited')
    expect(e.message).toMatch(/12 seconds/)
  })

  it('does not expose raw server errors but keeps the reference id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(500, { detail: 'secret stack', request_id: 'abc123' }))
    const e = await fail(request('/x'))
    expect(e.message).not.toMatch(/secret/)
    expect(e.message).toMatch(/abc123/)
    expect(e.retryable).toBe(true)
  })

  it('surfaces useful backend messages for upload problems', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(413, { detail: 'File is larger than the 100 MB limit.' }))
    const e = await fail(request('/documents', { method: 'POST' }))
    expect(e.kind).toBe('too_large')
    expect(e.message).toMatch(/100 MB/)
  })

  it('handles 204 and unreadable bodies', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 204 }))
    expect(await request('/x', { method: 'DELETE' })).toBeUndefined()
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('<html>', { status: 200 }))
    const e = await fail(request('/x'))
    expect(e.kind).toBe('unknown')
  })
})

describe('describeError', () => {
  it('always returns something presentable', () => {
    expect(describeError(new ApiError('network', 'Offline'))).toBe('Offline')
    expect(describeError(new Error('plain'))).toBe('plain')
    expect(describeError('weird', 'fallback')).toBe('fallback')
    expect(describeError(undefined)).toMatch(/something went wrong/i)
  })
})

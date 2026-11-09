import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, UNAUTHORIZED_EVENT, describeError, refreshSession, request, tokenStore } from './client'

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

describe('access token refresh', () => {
  const refreshed = (token = 'new-token') => json(200, { access_token: token, token_type: 'bearer' })

  it('an expired access token is renewed from the refresh cookie and the call is retried once', async () => {
    tokenStore.set('old')
    const seen: string[] = []
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      if (String(url).endsWith('/auth/refresh')) {
        expect(init?.credentials).toBe('include')
        expect(new Headers(init?.headers).get('X-Requested-With')).toBe('fetch')
        return refreshed()
      }
      const auth = new Headers(init?.headers).get('Authorization') ?? ''
      seen.push(auth)
      return auth === 'Bearer new-token' ? json(200, { ok: true }) : json(401, { detail: 'Not authenticated' })
    })
    expect(await request('/documents')).toEqual({ ok: true })
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
    expect(seen).toEqual(['Bearer old', 'Bearer new-token'])
    expect(tokenStore.get()).toBe('new-token')
    expect(spy).not.toHaveBeenCalled()
  })

  it('calls that fail together share a single refresh', async () => {
    tokenStore.set('old')
    let refreshCalls = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      if (String(url).endsWith('/auth/refresh')) {
        refreshCalls++
        return refreshed()
      }
      return new Headers(init?.headers).get('Authorization') === 'Bearer new-token'
        ? json(200, {})
        : json(401, { detail: 'x' })
    })
    await Promise.all([request('/a'), request('/b'), request('/c')])
    expect(refreshCalls).toBe(1)
  })

  it('a second 401 after a refresh signs the user out instead of looping', async () => {
    tokenStore.set('old')
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
      String(url).endsWith('/auth/refresh') ? refreshed() : json(401, { detail: 'x' }),
    )
    const e = await fail(request('/documents'))
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
    expect(e.kind).toBe('unauthorized')
    expect(tokenStore.get()).toBeNull()
    expect(spy).toHaveBeenCalledOnce()
  })

  it('an unreachable server during a refresh does not sign the user out', async () => {
    tokenStore.set('old')
    const spy = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, spy)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).endsWith('/auth/refresh')) throw new TypeError('Failed to fetch')
      return json(401, { detail: 'x' })
    })
    const e = await fail(request('/documents'))
    window.removeEventListener(UNAUTHORIZED_EVENT, spy)
    expect(e.kind).toBe('network')
    expect(tokenStore.hasSession()).toBe(true)
    expect(spy).not.toHaveBeenCalled()
  })

  it('refreshSession reports a rejected cookie as denied', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { detail: 'Session expired' }))
    expect(await refreshSession()).toBe('denied')
  })

  it('the access token is held in memory and only a flag is stored', () => {
    tokenStore.set('secret-token')
    expect(localStorage.getItem('fi_session')).toBe('1')
    expect(JSON.stringify({ ...localStorage })).not.toContain('secret-token')
    tokenStore.clear()
    expect(tokenStore.hasSession()).toBe(false)
  })
})

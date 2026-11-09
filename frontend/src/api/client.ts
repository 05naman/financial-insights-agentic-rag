const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const SESSION_KEY = 'fi_session'
export const UNAUTHORIZED_EVENT = 'fi:unauthorized'

/**
 * The short-lived access token lives in memory only (a script injected into the page can't read it from
 * storage). The long-lived refresh token is an HttpOnly cookie the browser keeps; the page never sees it.
 * `fi_session` in localStorage is just a "we were signed in" flag, so a reload knows to ask for a new
 * access token. It is not a secret.
 */
let accessToken: string | null = null

export const tokenStore = {
  get: () => accessToken,
  set: (t: string) => {
    accessToken = t
    try {
      localStorage.setItem(SESSION_KEY, '1')
    } catch {
      /* storage blocked: the session lasts until reload */
    }
  },
  /** True when a session probably exists (a refresh cookie may be waiting), even without an access token. */
  hasSession: () => {
    try {
      return localStorage.getItem(SESSION_KEY) === '1'
    } catch {
      return accessToken !== null
    }
  },
  clear: () => {
    accessToken = null
    try {
      localStorage.removeItem(SESSION_KEY)
    } catch {
      /* nothing to clear */
    }
  },
}

export type ErrorKind =
  | 'network'
  | 'timeout'
  | 'aborted'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'too_large'
  | 'validation'
  | 'rate_limited'
  | 'unavailable'
  | 'server'
  | 'unknown'

export class ApiError extends Error {
  status: number
  kind: ErrorKind
  retryAfter?: number
  requestId?: string
  constructor(kind: ErrorKind, message: string, status = 0, extra: { retryAfter?: number; requestId?: string } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.retryAfter = extra.retryAfter
    this.requestId = extra.requestId
  }
  /** Worth offering a "Try again" button for. */
  get retryable() {
    return ['network', 'timeout', 'rate_limited', 'unavailable', 'server'].includes(this.kind)
  }
}

/** A message that is safe and useful to show to a person, for any thrown value. */
export function describeError(e: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof DOMException && e.name === 'AbortError') return 'The request was cancelled.'
  if (e instanceof Error && e.message) return e.message
  return fallback
}

export const isAborted = (e: unknown) => e instanceof ApiError && e.kind === 'aborted'

const OFFLINE_MSG = "You appear to be offline. Check your connection and try again."
const NETWORK_MSG = "Can't reach the server. Check your connection, or try again in a moment."

function validationMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (!d || typeof d !== 'object') return ''
        const field = Array.isArray(d.loc) ? String(d.loc.filter((x: unknown) => x !== 'body').at(-1) ?? '') : ''
        const msg = String(d.msg ?? '').replace(/^value error, /i, '')
        return field && !msg.toLowerCase().startsWith(field.toLowerCase()) ? `${field}: ${msg}` : msg
      })
      .filter(Boolean)
    if (parts.length) return parts.join('. ')
  }
  return 'Some of the information was not valid.'
}

/** Turns a non-OK response into an ApiError with a human message. */
export async function errorFromResponse(res: Response, opts: { isAuthRequest?: boolean } = {}): Promise<ApiError> {
  let detail: unknown
  let requestId = res.headers.get('x-request-id') ?? undefined
  try {
    const body = await res.json()
    detail = body?.detail
    requestId = body?.request_id ?? requestId
  } catch {
    /* body was not JSON */
  }
  const text = typeof detail === 'string' ? detail : undefined
  const retryAfter = Number(res.headers.get('retry-after')) || undefined
  const extra = { retryAfter, requestId }

  switch (res.status) {
    case 401:
      if (opts.isAuthRequest) return new ApiError('unauthorized', text ?? 'Invalid email or password', 401, extra)
      return new ApiError('unauthorized', 'Your session has expired. Please sign in again.', 401, extra)
    case 403:
      return new ApiError('forbidden', text ?? "You don't have permission to do that.", 403, extra)
    case 404:
      return new ApiError('not_found', text ?? "We couldn't find that.", 404, extra)
    case 409:
      return new ApiError('conflict', text ?? 'That conflicts with something that already exists.', 409, extra)
    case 413:
      return new ApiError('too_large', text ?? 'That file is too large.', 413, extra)
    case 422:
      return new ApiError('validation', validationMessage(detail), 422, extra)
    case 429:
      return new ApiError(
        'rate_limited',
        retryAfter
          ? `You're going a little fast. Try again in ${retryAfter} seconds.`
          : "You're going a little fast. Wait a few seconds and try again.",
        429,
        extra,
      )
    case 502:
      return new ApiError('unavailable', text ?? 'An upstream service is unavailable. Please try again shortly.', 502, extra)
    case 503:
    case 504:
      return new ApiError('unavailable', 'The service is temporarily unavailable. Please try again shortly.', res.status, extra)
    default:
      if (res.status >= 500) {
        const ref = requestId ? ` (reference ${requestId})` : ''
        return new ApiError('server', `Something went wrong on our side${ref}. Please try again.`, res.status, extra)
      }
      return new ApiError('unknown', text ?? `Request failed (${res.status}).`, res.status, extra)
  }
}

/** Network-level failure (no response). */
export function networkError(): ApiError {
  return new ApiError('network', typeof navigator !== 'undefined' && navigator.onLine === false ? OFFLINE_MSG : NETWORK_MSG)
}

interface RequestOptions {
  timeoutMs?: number
  signal?: AbortSignal
  isAuthRequest?: boolean
  /** internal: this call already followed a token refresh, so a second 401 is final */
  retried?: boolean
}

let refreshing: Promise<'ok' | 'denied'> | null = null

/**
 * Trades the refresh cookie for a new access token. Calls made together share one request (the server
 * rotates the cookie, so two parallel refreshes would race). 'denied' means the session is really over;
 * a network failure throws, because an unreachable server must not sign the user out.
 */
export function refreshSession(): Promise<'ok' | 'denied'> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function doRefresh(): Promise<'ok' | 'denied'> {
  let res: Response
  try {
    res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Requested-With': 'fetch' },
    })
  } catch {
    throw networkError()
  }
  if (res.ok) {
    const body = (await res.json().catch(() => null)) as { access_token?: string } | null
    if (!body?.access_token) return 'denied'
    tokenStore.set(body.access_token)
    return 'ok'
  }
  if (res.status === 401 || res.status === 403) return 'denied'
  throw await errorFromResponse(res, { isAuthRequest: true })
}

export async function request<T>(path: string, init: RequestInit = {}, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, opts.timeoutMs ?? 30_000)
  const onAbort = () => controller.abort()
  opts.signal?.addEventListener('abort', onAbort)

  try {
    let res: Response
    try {
      res = await fetch(`${BASE}${path}`, {
        ...init,
        headers,
        signal: controller.signal,
        credentials: path.startsWith('/auth/') ? 'include' : init.credentials, // cookie only for auth routes
      })
    } catch {
      if (timedOut) throw new ApiError('timeout', 'The server took too long to respond. Please try again.')
      if (opts.signal?.aborted) throw new ApiError('aborted', 'The request was cancelled.')
      throw networkError()
    }
    if (!res.ok) {
      const err = await errorFromResponse(res, { isAuthRequest: opts.isAuthRequest })
      if (err.kind === 'unauthorized' && !opts.isAuthRequest) {
        // the access token expired (they last minutes): get a new one from the refresh cookie and retry once
        if (!opts.retried && (await refreshSession()) === 'ok') {
          return await request<T>(path, init, { ...opts, retried: true })
        }
        tokenStore.clear()
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
      }
      throw err
    }
    if (res.status === 204) return undefined as T
    try {
      return (await res.json()) as T
    } catch {
      throw new ApiError('unknown', 'The server sent a response we could not read.', res.status)
    }
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onAbort)
  }
}

export const apiUrl = (path: string) => `${BASE}${path}`

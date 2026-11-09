import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '../api/auth'
import { ApiError, UNAUTHORIZED_EVENT, describeError, refreshSession, tokenStore } from '../api/client'

/**
 * loading: asking the server whether the saved session is still good
 * authed / anon: known state
 * unreachable: we think we're signed in but the server could not be reached, so we must NOT log the user out
 */
type Status = 'loading' | 'authed' | 'anon' | 'unreachable'

interface AuthState {
  status: Status
  email: string | null
  /** Shown on the login page, e.g. after a session expires. */
  notice: string | null
  startupError: string | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => void
  retryStartup: () => Promise<void>
  clearNotice: () => void
}

const AuthContext = createContext<AuthState | null>(null)
const EXPIRED = 'Your session has expired. Please sign in again.'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>(() => (tokenStore.hasSession() ? 'loading' : 'anon'))
  const [email, setEmail] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [startupError, setStartupError] = useState<string | null>(null)

  const check = useCallback(async () => {
    if (!tokenStore.hasSession()) {
      setStatus('anon')
      return
    }
    try {
      // after a reload the access token (kept in memory) is gone: get a new one from the refresh cookie
      if (!tokenStore.get() && (await refreshSession()) === 'denied') {
        tokenStore.clear()
        setNotice(EXPIRED)
        setStatus('anon')
        return
      }
      const u = await authApi.me()
      setEmail(u.email)
      setStartupError(null)
      setStatus('authed')
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'unauthorized') {
        tokenStore.clear()
        setNotice(EXPIRED)
        setStatus('anon')
      } else {
        setStartupError(describeError(e))
        setStatus('unreachable')
      }
    }
  }, [])

  useEffect(() => {
    if (status === 'loading') check()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on first mount
  }, [])

  // any API call that comes back 401 ends the session everywhere
  useEffect(() => {
    const onExpired = () => {
      setEmail(null)
      setNotice(EXPIRED)
      setStatus('anon')
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onExpired)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onExpired)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      status,
      email,
      notice,
      startupError,
      signIn: async (e, p) => {
        await authApi.login(e, p)
        setEmail((await authApi.me()).email)
        setNotice(null)
        setStatus('authed')
      },
      signUp: async (e, p) => {
        await authApi.register(e, p)
        setEmail((await authApi.me()).email)
        setNotice(null)
        setStatus('authed')
      },
      signOut: () => {
        void authApi.logout() // end it on the server too, so the refresh token can't be reused
        tokenStore.clear()
        setEmail(null)
        setNotice(null)
        setStatus('anon')
      },
      retryStartup: check,
      clearNotice: () => setNotice(null),
    }),
    [status, email, notice, startupError, check],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

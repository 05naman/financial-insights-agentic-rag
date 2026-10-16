import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as chatApi from '../api/chat'
import { describeError } from '../api/client'
import { ONLINE_EVENT } from '../hooks/useOnline'
import type { Session } from '../types'
import { useToast } from '../ui/Toast'

interface SessionsState {
  sessions: Session[]
  loading: boolean
  /** Set when the last load failed; existing items stay visible. */
  error: string | null
  refresh: () => Promise<void>
  remove: (id: number) => Promise<boolean>
}

const SessionsContext = createContext<SessionsState | null>(null)

export function SessionsProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setSessions(await chatApi.listSessions())
      setError(null)
    } catch (e) {
      setError(describeError(e, "Couldn't load your history."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener(ONLINE_EVENT, refresh)
    return () => window.removeEventListener(ONLINE_EVENT, refresh)
  }, [refresh])

  const remove = useCallback(
    async (id: number) => {
      try {
        await chatApi.deleteSession(id)
        setSessions((s) => s.filter((x) => x.id !== id))
        return true
      } catch (e) {
        toast.error(`Couldn't delete that question. ${describeError(e)}`)
        return false
      }
    },
    [toast],
  )

  const value = useMemo(() => ({ sessions, loading, error, refresh, remove }), [sessions, loading, error, refresh, remove])
  return <SessionsContext.Provider value={value}>{children}</SessionsContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSessions() {
  const ctx = useContext(SessionsContext)
  if (!ctx) throw new Error('useSessions must be used inside SessionsProvider')
  return ctx
}

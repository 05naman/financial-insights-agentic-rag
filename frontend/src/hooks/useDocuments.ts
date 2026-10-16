import { useCallback, useEffect, useState } from 'react'
import { describeError } from '../api/client'
import { listDocuments } from '../api/documents'
import type { DocumentInfo } from '../types'
import { ONLINE_EVENT } from './useOnline'

/**
 * Loads the report list and polls while any report is still being processed.
 * A failed refresh keeps the last good list and sets `error` (so polling blips never blank the screen).
 */
export function useDocuments() {
  const [docs, setDocs] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setDocs(await listDocuments())
      setError(null)
    } catch (e) {
      setError(describeError(e, "Couldn't load your reports."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener(ONLINE_EVENT, refresh)
    return () => window.removeEventListener(ONLINE_EVENT, refresh)
  }, [refresh])

  const working = docs.some((d) => d.status === 'processing' || d.status === 'pending')
  useEffect(() => {
    if (!working) return
    const t = setInterval(refresh, 2500)
    return () => clearInterval(t)
  }, [working, refresh])

  return { docs, loading, error, refresh, working }
}

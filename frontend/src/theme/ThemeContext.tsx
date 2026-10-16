import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'
const KEY = 'fi_theme'

interface ThemeState {
  mode: ThemeMode
  resolved: 'light' | 'dark'
  setMode: (m: ThemeMode) => void
}

const ThemeContext = createContext<ThemeState | null>(null)

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode)
  const [sysDark, setSysDark] = useState(systemDark)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => setSysDark(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const resolved = mode === 'system' ? (sysDark ? 'dark' : 'light') : mode

  useEffect(() => {
    document.documentElement.dataset.theme = resolved
  }, [resolved])

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m)
    try {
      localStorage.setItem(KEY, m)
    } catch {
      /* private mode: keep in memory only */
    }
  }, [])

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved, setMode])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}

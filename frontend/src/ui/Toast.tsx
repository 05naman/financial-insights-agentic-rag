import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertIcon, CheckIcon, CloseIcon } from '../components/Icons'
import IconButton from './IconButton'

type Kind = 'error' | 'success' | 'info'
interface ToastItem {
  id: number
  kind: Kind
  message: string
  action?: { label: string; onClick: () => void }
}
interface ToastApi {
  error: (message: string, action?: ToastItem['action']) => void
  success: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)
const MAX_VISIBLE = 4

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
    setItems((all) => all.filter((t) => t.id !== id))
  }, [])

  const itemsRef = useRef<ToastItem[]>([])
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const push = useCallback(
    (kind: Kind, message: string, action?: ToastItem['action']) => {
      if (itemsRef.current.some((t) => t.message === message && t.kind === kind)) return // no duplicate stacks
      const id = nextId.current++
      // the timer is created here, not inside the state updater (React may run updaters twice)
      timers.current.set(id, setTimeout(() => dismiss(id), kind === 'error' ? 8000 : 4500))
      setItems((all) => [...all, { id, kind, message, action }].slice(-MAX_VISIBLE))
    },
    [dismiss],
  )

  useEffect(() => {
    const t = timers.current
    return () => t.forEach(clearTimeout)
  }, [])

  const api = useMemo<ToastApi>(
    () => ({
      error: (m, a) => push('error', m, a),
      success: (m) => push('success', m),
      info: (m) => push('info', m),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-4 sm:items-end">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`rise pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border bg-raised p-3.5 text-sm shadow-card ${
              t.kind === 'error' ? 'border-danger/40' : t.kind === 'success' ? 'border-primary/40' : 'border-line-strong'
            }`}
          >
            {t.kind === 'success' ? (
              <CheckIcon width={18} height={18} className="mt-0.5 shrink-0 text-primary" />
            ) : (
              <AlertIcon width={18} height={18} className={`mt-0.5 shrink-0 ${t.kind === 'error' ? 'text-danger' : 'text-muted'}`} />
            )}
            <p className="min-w-0 flex-1 text-ink/90">{t.message}</p>
            {t.action && (
              <button
                onClick={() => {
                  t.action?.onClick()
                  dismiss(t.id)
                }}
                className="shrink-0 rounded px-1 text-xs font-semibold text-primary underline underline-offset-4 hover:opacity-80 active:opacity-60"
              >
                {t.action.label}
              </button>
            )}
            <IconButton label="Dismiss notification" size="sm" className="-mr-1.5 -mt-1" onClick={() => dismiss(t.id)}>
              <CloseIcon width={14} height={14} />
            </IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}

import { useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useSessions } from '../context/SessionsContext'
import type { Session } from '../types'
import Alert from '../ui/Alert'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'
import { BookIcon, PlusIcon, TrashIcon } from './Icons'
import ThemeToggle from './ThemeToggle'
import Wordmark from './Wordmark'

function groupSessions(sessions: Session[]) {
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  const day = 86_400_000
  const groups: Record<string, Session[]> = { Today: [], Yesterday: [], Earlier: [] }
  for (const s of sessions) {
    // the API returns UTC timestamps without a zone marker
    const t = new Date(s.created_at.endsWith('Z') ? s.created_at : `${s.created_at}Z`).getTime()
    const key = t >= startOfToday.getTime() ? 'Today' : t >= startOfToday.getTime() - day ? 'Yesterday' : 'Earlier'
    groups[key].push(s)
  }
  return Object.entries(groups).filter(([, v]) => v.length)
}

export default function Rail({ onNavigate }: { onNavigate?: () => void }) {
  const { sessions, loading, error, refresh, remove } = useSessions()
  const { email, signOut } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const activeId = /^\/(\d+)$/.exec(pathname)?.[1]
  const [confirming, setConfirming] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)

  async function del(id: number) {
    if (confirming !== id) {
      setConfirming(id)
      setTimeout(() => setConfirming((c) => (c === id ? null : c)), 3000)
      return
    }
    setDeleting(id)
    const ok = await remove(id)
    setDeleting(null)
    setConfirming(null)
    if (ok && String(id) === activeId) navigate('/')
  }

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="px-5 pb-3 pt-5">
        <Link to="/" onClick={onNavigate} aria-label="Financial Insights home" className="inline-block rounded-md">
          <Wordmark />
        </Link>
      </div>
      <div className="px-3">
        <NavLink
          to="/"
          end
          onClick={onNavigate}
          title="New question (Ctrl/⌘ + K)"
          className="flex h-10 items-center gap-2 rounded-lg border border-line-strong bg-raised px-3 text-sm font-medium shadow-card transition duration-150 hover:border-primary hover:bg-primary-soft active:scale-[0.98]"
        >
          <PlusIcon width={16} height={16} />
          New question
        </NavLink>
      </div>

      <nav aria-label="History" className="mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {loading ? (
          <div className="space-y-2 px-1 pt-1" aria-hidden>
            {[78, 62, 70, 55].map((w, i) => (
              <div key={i} className="skeleton h-7" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : (
          <>
            {error && (
              <Alert kind="error" className="mb-3 !p-3 text-xs" onRetry={refresh}>
                {error}
              </Alert>
            )}
            {sessions.length === 0 && !error && <p className="px-2 pt-2 text-sm text-faint">Your questions will appear here.</p>}
            {groupSessions(sessions).map(([label, items]) => (
              <div key={label} className="mb-3">
                <h2 className="px-2 pb-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-faint">{label}</h2>
                <ul>
                  {items.map((s) => {
                    const active = String(s.id) === activeId
                    const isConfirming = confirming === s.id
                    return (
                      <li key={s.id} className="group relative">
                        <Link
                          to={`/${s.id}`}
                          onClick={onNavigate}
                          aria-current={active ? 'page' : undefined}
                          className={`block truncate rounded-md px-2 py-1.5 pr-9 text-[0.88rem] transition-colors active:bg-line ${
                            active ? 'bg-primary-soft font-medium text-primary' : 'text-ink/80 hover:bg-line/60'
                          } ${deleting === s.id ? 'opacity-50' : ''}`}
                        >
                          {s.title}
                        </Link>
                        <div className="absolute right-1 top-1/2 -translate-y-1/2">
                          {isConfirming ? (
                            <Button size="sm" variant="danger-soft" className="h-6 px-2" loading={deleting === s.id} onClick={() => del(s.id)}>
                              Delete?
                            </Button>
                          ) : (
                            <IconButton
                              label={`Delete ${s.title}`}
                              variant="danger"
                              size="sm"
                              className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                              onClick={() => del(s.id)}
                            >
                              <TrashIcon width={14} height={14} />
                            </IconButton>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </>
        )}
      </nav>

      <div className="space-y-3 border-t border-line p-3">
        <NavLink
          to="/library"
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex h-9 items-center gap-2 rounded-md px-2 text-sm font-medium transition duration-150 active:scale-[0.98] ${
              isActive ? 'bg-primary-soft text-primary' : 'text-ink/80 hover:bg-line/60 active:bg-line'
            }`
          }
        >
          <BookIcon width={16} height={16} />
          Library
        </NavLink>
        <div className="flex items-center justify-between gap-2 px-1">
          <ThemeToggle />
          <Button variant="link" className="text-xs !text-muted hover:!text-ink" onClick={signOut}>
            Sign out
          </Button>
        </div>
        <p className="truncate px-1 text-xs text-faint" title={email ?? ''}>
          {email}
        </p>
      </div>
    </div>
  )
}

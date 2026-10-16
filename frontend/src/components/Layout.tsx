import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { SessionsProvider } from '../context/SessionsContext'
import Button from '../ui/Button'
import ErrorBoundary from '../ui/ErrorBoundary'
import IconButton from '../ui/IconButton'
import NetworkBanner from '../ui/NetworkBanner'
import { CloseIcon, MenuIcon } from './Icons'
import Rail from './Rail'
import Wordmark from './Wordmark'

function ServerDown({ message, onRetry }: { message: string | null; onRetry: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const { signOut } = useAuth()
  return (
    <div className="grid min-h-dvh place-items-center px-6 text-center">
      <div className="max-w-sm">
        <div className="mb-6 flex justify-center">
          <Wordmark />
        </div>
        <h1 className="font-serif text-3xl font-medium tracking-tight">Can't reach the server</h1>
        <p className="mt-2 text-sm text-muted">
          {message && !/^can't reach/i.test(message)
            ? message
            : 'Check your connection. If it is fine, the service may still be starting up.'}
        </p>
        <p className="mt-1 text-sm text-muted">You are still signed in. Nothing was lost.</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button
            loading={busy}
            loadingText="Checking…"
            onClick={async () => {
              setBusy(true)
              try {
                await onRetry()
              } finally {
                setBusy(false)
              }
            }}
          >
            Try again
          </Button>
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function Layout() {
  const { status, startupError, retryStartup } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [drawer, setDrawer] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        navigate('/')
        requestAnimationFrame(() => document.getElementById('composer')?.focus())
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  useEffect(() => {
    if (!drawer) return
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false)
    window.addEventListener('keydown', onEsc)
    return () => window.removeEventListener('keydown', onEsc)
  }, [drawer])

  if (status === 'loading') {
    return (
      <div className="grid h-dvh place-items-center">
        <div className="pulse-dot h-2.5 w-2.5 rounded-full bg-accent" role="status" aria-label="Loading" />
      </div>
    )
  }
  if (status === 'unreachable') return <ServerDown message={startupError} onRetry={retryStartup} />
  if (status === 'anon') return <Navigate to="/login" replace />

  return (
    <SessionsProvider>
      <div className="flex h-dvh flex-col">
        <NetworkBanner />
        <div className="flex min-h-0 flex-1">
          <aside className="hidden w-[272px] shrink-0 border-r border-line lg:block">
            <Rail />
          </aside>

          {drawer && (
            <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
              <button
                aria-label="Close menu"
                className="absolute inset-0 bg-ink/40 transition-colors active:bg-ink/50"
                onClick={() => setDrawer(false)}
              />
              <div className="sheet-in absolute inset-y-0 left-0 w-[290px] max-w-[85vw] border-r border-line shadow-card">
                <Rail onNavigate={() => setDrawer(false)} />
              </div>
            </div>
          )}

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex items-center gap-3 border-b border-line px-4 py-2.5 lg:hidden">
              <IconButton label={drawer ? 'Close menu' : 'Open menu'} aria-expanded={drawer} onClick={() => setDrawer((d) => !d)}>
                {drawer ? <CloseIcon /> : <MenuIcon />}
              </IconButton>
              <Wordmark />
            </header>
            <main className="min-h-0 flex-1">
              <ErrorBoundary inline key={pathname.startsWith('/library') ? 'library' : 'ask'}>
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
        </div>
      </div>
    </SessionsProvider>
  )
}

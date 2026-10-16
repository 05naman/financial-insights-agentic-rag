import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { describeError } from '../api/client'
import { EyeIcon } from '../components/Icons'
import ThemeToggle from '../components/ThemeToggle'
import Wordmark from '../components/Wordmark'
import { useAuth } from '../context/AuthContext'
import Alert from '../ui/Alert'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'

/** A static, decorative "page from a report" that shows the product idea: a figure and its footnote. */
function SpecimenPage() {
  const rows: [string, string, string][] = [
    ['Revenue from operations', '1,89,866', '1,74,831'],
    ['Profit before tax', '47,505', '44,177'],
    ['Profit for the year', '35,391', '32,912'],
  ]
  return (
    <div aria-hidden data-testid="specimen" className="relative mx-auto w-full max-w-[400px] -rotate-[1.2deg] rounded-md border border-line-strong bg-raised p-6 shadow-card [@media(max-height:780px)]:hidden">
      <p className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-faint">Standalone statement of profit and loss</p>
      <p className="mt-1 font-serif text-lg">For the year ended March 31, 2024</p>
      <p className="mt-0.5 text-[0.7rem] text-muted">(Rs in crore)</p>
      <div className="mt-4 border-t border-ink/70">
        {rows.map(([name, a, b], i) => (
          <div key={name} className={`flex items-baseline py-2 text-[0.82rem] ${i ? 'border-t border-line' : ''}`}>
            <span className="flex-1">
              {name}
              {i === 0 && (
                <sup className="num ml-0.5 rounded-[4px] bg-accent-soft px-[4px] text-[0.6rem] text-accent-ink">1</sup>
              )}
            </span>
            <span className="num w-20 text-right">{a}</span>
            <span className="num w-20 text-right text-muted">{b}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 flex items-center gap-2 text-[0.72rem] text-muted">
        <span className="num grid h-4 min-w-4 place-items-center rounded-[4px] bg-accent-soft px-1 text-[0.6rem] text-accent-ink">1</span>
        BHIT · FY2024 · page 5
      </div>
    </div>
  )
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function LoginPage() {
  const { status, signIn, signUp, notice, clearNotice } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})
  const [busy, setBusy] = useState(false)

  if (status === 'authed') return <Navigate to="/" replace />

  function validate() {
    const next: typeof fieldErrors = {}
    if (!EMAIL.test(email.trim())) next.email = 'Enter a valid email address.'
    if (password.length < 8) next.password = 'Use at least 8 characters.'
    setFieldErrors(next)
    return Object.keys(next).length === 0
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!validate()) return
    setBusy(true)
    try {
      await (mode === 'login' ? signIn : signUp)(email.trim(), password)
      navigate('/')
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const input = (invalid: boolean) =>
    `w-full rounded-lg border bg-raised px-3.5 py-2.5 text-[0.95rem] transition-colors placeholder:text-faint hover:border-faint focus:outline-none ${
      invalid ? 'border-danger focus:border-danger' : 'border-line-strong focus:border-primary'
    }`

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden flex-col gap-10 border-r border-line bg-surface p-10 lg:flex xl:p-12">
        <Wordmark size="lg" />
        <div className="my-auto">
          <h1 className="font-serif text-[clamp(2.4rem,4vw,3.1rem)] font-medium leading-[1.04] tracking-tight text-balance">
            Annual reports, read <em className="text-accent-ink">carefully</em>.
          </h1>
          <p className="mt-5 max-w-[30rem] text-[1.02rem] text-muted text-pretty">
            Ask a question, get an answer with the page it came from. Numbers are calculated by a calculator and checked
            against the source, never guessed.
          </p>
        </div>
        <SpecimenPage />
        <p className="text-xs text-faint">Research information, not investment advice.</p>
      </section>

      <main className="relative flex items-center justify-center p-6">
        <div className="absolute right-5 top-5">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-[22rem]">
          <div className="mb-8 lg:hidden">
            <Wordmark />
          </div>
          <h2 className="font-serif text-[1.9rem] font-medium tracking-tight">
            {mode === 'login' ? 'Welcome back' : 'Create your account'}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {mode === 'login' ? 'Sign in to continue to your questions.' : 'It takes a few seconds.'}
          </p>

          {notice && (
            <Alert kind="warning" className="mt-5" onDismiss={clearNotice}>
              {notice}
            </Alert>
          )}

          <form onSubmit={submit} noValidate className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoFocus
                autoComplete="email"
                value={email}
                disabled={busy}
                aria-invalid={!!fieldErrors.email}
                aria-describedby={fieldErrors.email ? 'email-error' : undefined}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (fieldErrors.email) setFieldErrors((f) => ({ ...f, email: undefined }))
                }}
                className={`${input(!!fieldErrors.email)} disabled:opacity-60`}
                placeholder="you@example.com"
              />
              {fieldErrors.email && (
                <p id="email-error" className="mt-1 text-xs text-danger">
                  {fieldErrors.email}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={show ? 'text' : 'password'}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  value={password}
                  disabled={busy}
                  aria-invalid={!!fieldErrors.password}
                  aria-describedby={fieldErrors.password ? 'password-error' : undefined}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }))
                  }}
                  className={`${input(!!fieldErrors.password)} pr-11 disabled:opacity-60`}
                  placeholder="At least 8 characters"
                />
                <IconButton
                  label={show ? 'Hide password' : 'Show password'}
                  aria-pressed={show}
                  size="sm"
                  className="absolute right-2 top-1/2 -translate-y-1/2"
                  onClick={() => setShow((v) => !v)}
                >
                  <EyeIcon width={17} height={17} />
                </IconButton>
              </div>
              {fieldErrors.password && (
                <p id="password-error" className="mt-1 text-xs text-danger">
                  {fieldErrors.password}
                </p>
              )}
            </div>

            <div aria-live="polite">{error && <Alert kind="error">{error}</Alert>}</div>

            <Button type="submit" size="lg" fullWidth loading={busy} loadingText={mode === 'login' ? 'Signing in…' : 'Creating account…'}>
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted">
            {mode === 'login' ? 'New here? ' : 'Already have an account? '}
            <Button
              variant="link"
              className="inline font-medium"
              disabled={busy}
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError('')
                setFieldErrors({})
              }}
            >
              {mode === 'login' ? 'Create an account' : 'Sign in'}
            </Button>
          </p>
        </div>
      </main>
    </div>
  )
}

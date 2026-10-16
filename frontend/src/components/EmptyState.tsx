import { Link } from 'react-router-dom'
import Alert from '../ui/Alert'
import type { DocumentInfo } from '../types'
import { ArrowRightIcon } from './Icons'
import CoverageGrid from './CoverageGrid'

function suggestions(docs: DocumentInfo[]): string[] {
  const ready = docs.filter((d) => d.status === 'ready')
  if (!ready.length) return []
  const ticker = ready[0].ticker
  const years = ready.filter((d) => d.ticker === ticker).map((d) => d.fiscal_year).sort()
  const last = years.at(-1)!
  const out = [`What was ${ticker}'s revenue from operations in FY${last}?`]
  if (years.length > 1) out.push(`How did ${ticker}'s revenue change from FY${years[0]} to FY${last}?`)
  out.push(`What are the key risks ${ticker} flags in its FY${last} report?`)
  const other = ready.find((d) => d.ticker !== ticker)
  if (other) out.push(`Compare the profit after tax of ${ticker} and ${other.ticker} in FY${last}.`)
  return out
}

interface Props {
  docs: DocumentInfo[]
  loading: boolean
  error?: string | null
  onRetry?: () => void | Promise<unknown>
  disabled?: boolean
  onPick: (q: string) => void
}

export default function EmptyState({ docs, loading, error, onRetry, disabled, onPick }: Props) {
  const ideas = suggestions(docs)
  const none = !loading && !error && docs.length === 0
  return (
    <div className="rise pt-6 sm:pt-12">
      <h1 className="font-serif text-[2.6rem] font-medium leading-[1.05] tracking-tight sm:text-[3.4rem]">
        Ask the reports<span className="text-accent">.</span>
      </h1>
      <p className="mt-4 max-w-[34rem] text-[1.02rem] text-muted text-pretty">
        Questions about Indian company annual reports, answered with page citations. Every number is checked against its
        source before you see it.
      </p>

      {error && docs.length === 0 ? (
        <Alert kind="error" title="Couldn't load your reports" className="mt-10" onRetry={onRetry}>
          {error}
        </Alert>
      ) : none ? (
        <div className="mt-10 rounded-xl border border-dashed border-line-strong p-6">
          <p className="font-medium">No reports yet</p>
          <p className="mt-1 text-sm text-muted">Add an annual report PDF to start asking questions.</p>
          <Link to="/library" className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-medium text-bg transition duration-150 hover:opacity-90 active:scale-[0.98] active:opacity-80">
            Add a report <ArrowRightIcon width={15} height={15} />
          </Link>
        </div>
      ) : (
        <div className="mt-10 grid gap-10 md:grid-cols-[1.1fr_1fr]">
          <section aria-label="Suggested questions">
            <h2 className="mb-2 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Try asking</h2>
            {loading ? (
              <div className="space-y-2" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="skeleton h-11 w-full" />
                ))}
              </div>
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {ideas.map((q) => (
                  <li key={q}>
                    <button
                      onClick={() => onPick(q)}
                      disabled={disabled}
                      className="group flex w-full items-center gap-3 rounded-sm py-3 text-left transition-colors hover:bg-primary-soft/50 active:bg-primary-soft disabled:pointer-events-none disabled:opacity-50"
                    >
                      <span className="flex-1 font-serif text-[1.02rem] leading-snug">{q}</span>
                      <ArrowRightIcon width={16} height={16} className="shrink-0 text-faint transition-all group-hover:translate-x-1 group-hover:text-accent" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-label="Report coverage">
            <h2 className="mb-2 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">In the library</h2>
            <CoverageGrid docs={docs} loading={loading} />
            <Link to="/library" className="mt-3 inline-block rounded-sm text-sm text-primary underline decoration-primary/30 underline-offset-4 hover:decoration-primary active:opacity-70">
              Manage reports
            </Link>
          </section>
        </div>
      )}
    </div>
  )
}

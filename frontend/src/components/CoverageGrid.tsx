import type { DocumentInfo } from '../types'

const STATUS_LABEL: Record<DocumentInfo['status'], string> = {
  ready: 'Ready',
  processing: 'Reading pages',
  pending: 'Queued',
  failed: 'Failed',
}

/** Company × year matrix: shows at a glance which reports the assistant can answer from. */
export default function CoverageGrid({ docs, loading }: { docs: DocumentInfo[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="space-y-2" aria-hidden>
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-9 w-full" />
        ))}
      </div>
    )
  }
  if (!docs.length) return null
  const tickers = [...new Set(docs.map((d) => d.ticker))].sort()
  const years = [...new Set(docs.map((d) => d.fiscal_year))].sort()
  const cell = (t: string, y: number) => docs.find((d) => d.ticker === t && d.fiscal_year === y)

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-y-1 text-sm">
        <thead>
          <tr>
            <th className="w-24 text-left text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Company</th>
            {years.map((y) => (
              <th key={y} className="num px-2 text-center text-[0.72rem] font-medium text-muted">
                FY{y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tickers.map((t) => (
            <tr key={t}>
              <td className="font-medium">{t}</td>
              {years.map((y) => {
                const d = cell(t, y)
                return (
                  <td key={y} className="px-2 text-center">
                    <span
                      title={d ? `${t} FY${y}: ${STATUS_LABEL[d.status]}` : `${t} FY${y}: not added`}
                      className={`mx-auto block h-6 rounded-md border ${
                        !d
                          ? 'border-dashed border-line-strong'
                          : d.status === 'ready'
                            ? 'border-primary/30 bg-primary-soft'
                            : d.status === 'failed'
                              ? 'border-danger/40 bg-danger-soft'
                              : 'pulse-dot border-accent/40 bg-accent-soft'
                      }`}
                    >
                      {d?.status === 'ready' && (
                        <span className="num text-[0.65rem] leading-6 text-primary">{d.page_count}p</span>
                      )}
                    </span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

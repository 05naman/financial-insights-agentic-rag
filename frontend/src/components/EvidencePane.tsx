import { useEffect, useMemo, useState } from 'react'
import { excerptAround, figuresIn, hasUnreadable } from '../lib/citations'
import type { Footnote } from '../lib/citations'
import IconButton from '../ui/IconButton'
import { CloseIcon, CollapseIcon, ExpandIcon } from './Icons'
import MarkdownView from './MarkdownView'

interface Props {
  footnotes: Footnote[]
  activeKey: string | null
  answer: string
  onSelect: (key: string) => void
  onClose: () => void
  expanded?: boolean
  onToggleExpand?: () => void
}

export default function EvidencePane({
  footnotes,
  activeKey,
  answer,
  onSelect,
  onClose,
  expanded,
  onToggleExpand,
}: Props) {
  const active = footnotes.find((f) => f.key === activeKey) ?? footnotes[0]
  const figures = useMemo(() => figuresIn(answer), [answer])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
      if (e.key === 'Escape' && !typing) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!active) return null
  const c = active.citation
  return (
    <aside aria-label="Source passage" className="sheet-in flex h-full flex-col border-l border-line bg-surface">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Evidence</h2>
        <div className="ml-2 flex flex-wrap gap-1">
          {footnotes.map((f) => (
            <button
              key={f.key}
              onClick={() => onSelect(f.key)}
              aria-label={`Source ${f.n}`}
              aria-current={f.key === active.key}
              className={`num grid h-6 min-w-6 place-items-center rounded-[6px] px-1.5 text-xs font-medium transition duration-150 active:scale-90 ${
                f.key === active.key ? 'bg-accent text-bg' : 'bg-accent-soft text-accent-ink hover:bg-accent/30'
              }`}
            >
              {f.n}
            </button>
          ))}
        </div>
        {onToggleExpand && (
          <IconButton
            label={expanded ? 'Narrow the panel' : 'Widen the panel for big tables'}
            size="sm"
            className="ml-auto hidden lg:grid"
            onClick={onToggleExpand}
          >
            {expanded ? <CollapseIcon width={16} height={16} /> : <ExpandIcon width={16} height={16} />}
          </IconButton>
        )}
        <IconButton label="Close evidence" size="sm" className={onToggleExpand ? '' : 'ml-auto'} onClick={onClose}>
          <CloseIcon width={16} height={16} />
        </IconButton>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <div key={active.key} className="rise">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Annual report</p>
          <h3 className="mt-1 font-serif text-xl font-medium">
            {c.ticker} <span className="text-faint">·</span> FY{c.fiscal_year}
          </h3>
          <p className="num mt-0.5 text-xs text-muted">Page {c.page}</p>
          {hasUnreadable(c.text) && (
            <p role="note" className="mt-3 rounded-md bg-accent-soft px-3 py-2 text-xs text-accent-ink">
              Some characters on this page could not be read from the PDF (shown as ▯). The figures are usually
              fine; check the original page if in doubt.
            </p>
          )}
          <Quote key={active.key} text={c.text} figures={figures} />
          <p className="mt-3 text-xs text-faint">
            {/^\s*\|/m.test(c.text) && 'Wide tables scroll sideways. '}Figures that also appear in the answer are{' '}
            <mark className="rounded bg-accent/25 px-0.5 text-inherit">highlighted</mark>.
          </p>
        </div>
      </div>
    </aside>
  )
}

function Quote({ text, figures }: { text: string; figures: Set<string> }) {
  const excerpt = useMemo(() => excerptAround(text, figures), [text, figures])
  const [full, setFull] = useState(false)
  const shown = excerpt && !full ? excerpt : text
  return (
    <>
      <div className="mt-4 rounded-lg border border-line bg-raised p-4 shadow-card">
        <MarkdownView markdown={shown} variant="passage" highlight={figures} />
      </div>
      {excerpt && (
        <button
          type="button"
          onClick={() => setFull((v) => !v)}
          className="mt-2 text-xs font-medium text-primary underline-offset-2 hover:underline"
        >
          {full ? 'Show only the key sentences' : 'Show the full passage'}
        </button>
      )}
    </>
  )
}

import { useMemo, useState } from 'react'
import { cleanUnreadable, linkifyCitations } from '../lib/citations'
import { describeStep, verdictOf } from '../lib/steps'
import type { AgentStep, ChatMessage } from '../types'
import Alert from '../ui/Alert'
import { useToast } from '../ui/Toast'
import { CheckIcon, ChevronIcon, CopyIcon } from './Icons'
import MarkdownView from './MarkdownView'
import SkeletonNote from './SkeletonNote'
import ThinkingTicker from './ThinkingTicker'
import VerifiedBadge from './VerifiedBadge'

export interface Note {
  id: string
  question: string
  status: 'loading' | 'done' | 'error'
  message?: ChatMessage
  steps: AgentStep[]
  error?: string
}

interface Props {
  note: Note
  activeKey: string | null
  onCite: (noteId: string, key: string) => void
  onRetry: (note: Note) => void
}

const LLM_DOWN = /language model is unavailable/i

export default function NoteView({ note, activeKey, onCite, onRetry }: Props) {
  return (
    <article data-note-id={note.id} className="rise scroll-mt-4 border-b border-line py-8 first:pt-2 last:border-b-0">
      <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Question</p>
      <h2 className="font-serif text-[1.55rem] font-medium leading-snug tracking-tight text-pretty">
        {note.question}
      </h2>
      <div className="mt-6">
        {note.status === 'loading' && (
          <div className="space-y-7">
            <ThinkingTicker steps={note.steps} />
            <SkeletonNote />
          </div>
        )}
        {note.status === 'error' && <ErrorState message={note.error} onRetry={() => onRetry(note)} />}
        {note.status === 'done' && note.message && (
          <Answer note={note} message={note.message} activeKey={activeKey} onCite={onCite} onRetry={onRetry} />
        )}
      </div>
    </article>
  )
}

function ErrorState({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <Alert kind="error" title="That didn't go through" onRetry={onRetry}>
      {message || 'Something went wrong while answering.'}
    </Alert>
  )
}

function Answer({
  note,
  message,
  activeKey,
  onCite,
  onRetry,
}: {
  note: Note
  message: ChatMessage
  activeKey: string | null
  onCite: Props['onCite']
  onRetry: Props['onRetry']
}) {
  const { markdown, footnotes } = useMemo(
    () => linkifyCitations(message.content, message.citations),
    [message.content, message.citations],
  )
  const steps = message.steps.length ? message.steps : note.steps
  const verdict = verdictOf(steps, message.content)
  const [copied, setCopied] = useState(false)
  const toast = useToast()

  if (LLM_DOWN.test(message.content)) {
    return (
      <ErrorState
        message="The language model is rate-limited or unreachable right now. Your question was saved; try again in a moment."
        onRetry={() => onRetry(note)}
      />
    )
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content) // keeps the [TICKER FYyyyy p.N] citations
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      toast.error("Couldn't copy to the clipboard. Select the text and copy it manually.")
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <VerifiedBadge verdict={verdict} />
      </div>
      <MarkdownView
        markdown={markdown}
        variant="note"
        activeKey={activeKey}
        onCite={(key) => onCite(note.id, key)}
      />

      {footnotes.length > 0 && (
        <section aria-label="Sources" className="mt-6 rounded-lg border border-line bg-surface">
          <h3 className="border-b border-line px-4 py-2 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">
            Sources
          </h3>
          <ol>
            {footnotes.map((f) => (
              <li key={f.key} className="border-t border-line first:border-t-0">
                <button
                  onClick={() => onCite(note.id, f.key)}
                  className={`group flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-primary-soft active:bg-primary-soft/70 ${
                    f.key === activeKey ? 'bg-primary-soft' : ''
                  }`}
                >
                  <span className="num mt-0.5 grid h-5 min-w-5 place-items-center rounded-[5px] bg-accent-soft px-1 text-[0.68rem] font-medium text-accent-ink">
                    {f.n}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">
                      {f.citation.ticker} <span className="text-faint">·</span> FY{f.citation.fiscal_year}{' '}
                      <span className="text-faint">·</span> page {f.citation.page}
                    </span>
                    <span className="block truncate text-[0.8rem] text-muted">
                      {cleanUnreadable(f.citation.text).replace(/[|#*-]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120)}
                    </span>
                  </span>
                  <ChevronIcon width={16} height={16} className="mt-1 text-faint transition-transform group-hover:translate-x-0.5" />
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="mt-4 flex items-center gap-4 text-xs text-muted">
        <button onClick={copy} className="inline-flex items-center gap-1.5 rounded-sm transition duration-150 hover:text-ink active:scale-95 active:opacity-70">
          {copied ? <CheckIcon width={14} height={14} /> : <CopyIcon width={14} height={14} />}
          {copied ? 'Copied' : 'Copy answer'}
        </button>
        {steps.length > 0 && <Trail steps={steps} />}
      </div>
    </div>
  )
}

function Trail({ steps }: { steps: AgentStep[] }) {
  const [open, setOpen] = useState(false)
  const shown = steps.filter((s) => s.node !== 'finalize')
  return (
    <div className="min-w-0 flex-1">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex items-center gap-1 rounded-sm transition duration-150 hover:text-ink active:opacity-70">
        <ChevronIcon width={14} height={14} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
        How this was answered
      </button>
      {open && (
        <ol className="rise mt-3 space-y-2 border-l border-line pl-4">
          {shown.map((s, i) => {
            const { label, detail } = describeStep(s)
            return (
              <li key={i} className="text-[0.82rem] leading-snug">
                <span className="text-ink/85">{label}</span>
                {detail && <span className="block text-faint">{detail}</span>}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

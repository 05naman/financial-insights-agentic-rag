import { useEffect, useRef } from 'react'
import type { KeyboardEvent } from 'react'
import type { Mode } from '../types'
import IconButton from '../ui/IconButton'
import { ArrowUpIcon, StopIcon } from './Icons'

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: 'agentic', label: 'Agent', hint: 'Plans, searches, calculates and verifies' },
  { value: 'hybrid', label: 'Hybrid', hint: 'One search (keyword + meaning), one answer' },
  { value: 'naive', label: 'Naive', hint: 'Baseline: meaning-only search, one answer' },
]

interface Props {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onStop: () => void
  busy: boolean
  mode: Mode
  onMode: (m: Mode) => void
  inputRef: React.RefObject<HTMLTextAreaElement | null>
}

export default function Composer({ value, onChange, onSubmit, onStop, busy, mode, onMode, inputRef }: Props) {
  const innerRef = useRef<HTMLTextAreaElement | null>(null)
  const ref = inputRef ?? innerRef

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`
  }, [value, ref])

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!busy && value.trim().length >= 3) onSubmit()
    }
  }

  const canSend = value.trim().length >= 3 && !busy
  return (
    <div className="rounded-2xl border border-line-strong bg-raised shadow-card transition-colors focus-within:border-primary">
      <label htmlFor="composer" className="sr-only">
        Ask a question about the reports
      </label>
      <textarea
        id="composer"
        ref={ref}
        value={value}
        rows={1}
        maxLength={1000}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about revenue, margins, risks…"
        className="block w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[0.95rem] placeholder:text-faint focus:outline-none"
      />
      <div className="flex items-center gap-2 px-2.5 pb-2.5 pt-1">
        <div role="radiogroup" aria-label="Answering mode" className="inline-flex rounded-full bg-surface p-0.5 text-xs">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={mode === m.value}
              title={m.hint}
              disabled={busy}
              onClick={() => onMode(m.value)}
              className={`rounded-full px-2.5 py-1 font-medium transition duration-150 active:scale-95 disabled:pointer-events-none disabled:opacity-50 ${
                mode === m.value ? 'bg-ink text-bg' : 'text-muted hover:bg-line/70 hover:text-ink'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className="ml-auto" />
        {busy ? (
          <IconButton label="Stop answering" variant="outline" size="md" onClick={onStop} className="size-8">
            <StopIcon width={14} height={14} />
          </IconButton>
        ) : (
          <IconButton label="Send question" title="Send (Enter). Shift+Enter for a new line" variant="primary" onClick={onSubmit} disabled={!canSend} className="size-8">
            <ArrowUpIcon width={16} height={16} strokeWidth={2.2} />
          </IconButton>
        )}
      </div>
    </div>
  )
}

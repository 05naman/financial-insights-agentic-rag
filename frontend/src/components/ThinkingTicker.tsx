import { useEffect, useState } from 'react'
import { describeStep, pendingLabel } from '../lib/steps'
import type { AgentStep } from '../types'
import { CheckIcon } from './Icons'

export default function ThinkingTicker({ steps }: { steps: AgentStep[] }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const done = steps.filter((s) => s.node !== 'finalize')
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <div className="flex items-center gap-2.5 text-sm font-medium text-ink">
        <span className="pulse-dot h-2 w-2 rounded-full bg-accent" />
        <span key={pendingLabel(steps)} className="rise">
          {pendingLabel(steps)}…
        </span>
        <span className="num ml-auto text-xs text-faint">{seconds}s</span>
      </div>
      {done.length > 0 && (
        <ol className="space-y-1.5 border-l border-line pl-4">
          {done.map((s, i) => {
            const { label, detail } = describeStep(s)
            return (
              <li key={i} className="rise relative text-[0.82rem] leading-snug text-muted">
                <CheckIcon
                  width={12}
                  height={12}
                  className="absolute -left-[22px] top-[3px] rounded-full bg-bg text-primary"
                  strokeWidth={2.4}
                />
                <span className="text-ink/80">{label}</span>
                {detail && <span className="block truncate text-faint">{detail}</span>}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

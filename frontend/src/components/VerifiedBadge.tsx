import type { Verdict } from '../lib/steps'
import { AlertIcon, ShieldCheckIcon } from './Icons'

export default function VerifiedBadge({ verdict }: { verdict: Verdict }) {
  if (verdict === 'none') return null
  const ok = verdict === 'verified'
  return (
    <span
      title={
        ok
          ? 'Every number in this answer was found in the cited passages or the calculator output.'
          : 'Some figures could not be matched to the cited passages. Check the sources.'
      }
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
        ok
          ? 'border-primary/30 bg-primary-soft text-primary'
          : 'border-danger/30 bg-danger-soft text-danger'
      }`}
    >
      {ok ? <ShieldCheckIcon width={14} height={14} /> : <AlertIcon width={14} height={14} />}
      {ok ? 'Figures verified' : 'Check the sources'}
    </span>
  )
}

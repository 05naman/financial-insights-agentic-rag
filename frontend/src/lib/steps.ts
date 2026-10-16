import type { AgentStep } from '../types'

interface SubQ {
  query: string
  tickers: string[]
  fiscal_years: number[]
}
interface Search {
  query: string
  hits: string[]
}

export interface StepLine {
  label: string
  detail?: string
}

const scope = (s: SubQ) => [...s.tickers, ...s.fiscal_years.map((y) => `FY${y}`)].join(' · ')

/** One human sentence per agent step, written for the live ticker and the timeline. */
export function describeStep(step: AgentStep): StepLine {
  switch (step.node) {
    case 'plan': {
      if (step.out_of_scope) return { label: 'Not a question about the reports' }
      const subs = (step.sub_questions as SubQ[]) ?? []
      const where = [...new Set(subs.map(scope).filter(Boolean))].join(', ')
      return {
        label: subs.length > 1 ? `Split into ${subs.length} lookups` : 'Planned the lookup',
        detail: where || undefined,
      }
    }
    case 'retrieve': {
      const searches = (step.searches as Search[]) ?? []
      const pages = [...new Set(searches.flatMap((s) => s.hits))]
      return {
        label: Number(step.round) > 1 ? 'Searched again with new wording' : 'Searched the reports',
        detail: pages.length ? `${pages.length} passages, e.g. ${pages.slice(0, 2).join(' · ')}` : 'nothing found',
      }
    }
    case 'grade':
      return step.sufficient
        ? { label: 'Evidence looks sufficient' }
        : { label: 'Evidence incomplete', detail: String(step.missing || '') || undefined }
    case 'compute': {
      const calcs = (step.calculations as { label: string; value: number }[]) ?? []
      return calcs.length
        ? { label: `Ran ${calcs.length} calculation${calcs.length > 1 ? 's' : ''}`, detail: calcs.map((c) => `${c.label} = ${c.value}`).join(' · ') }
        : { label: 'No calculation needed' }
    }
    case 'synthesize':
      return { label: Number(step.attempt) > 1 ? 'Rewrote the answer' : 'Wrote the answer' }
    case 'verify': {
      if (step.skipped) return { label: 'Verification skipped' }
      const problems = (step.problems as string[]) ?? []
      return step.grounded
        ? { label: 'Checked every figure against the sources' }
        : { label: 'Found unsupported figures', detail: problems.join('; ') }
    }
    default:
      return { label: step.node }
  }
}

/** What the agent is doing right now, shown in the live ticker. */
export function pendingLabel(steps: AgentStep[]): string {
  const last = steps.filter((s) => s.node !== 'finalize').at(-1)
  if (!last) return 'Reading your question'
  switch (last.node) {
    case 'plan':
      return 'Searching the reports'
    case 'retrieve':
      return 'Judging the evidence'
    case 'grade':
      return last.sufficient ? 'Running the numbers' : 'Searching again'
    case 'compute':
      return 'Writing the answer'
    case 'synthesize':
      return 'Verifying every figure'
    case 'verify':
      return last.grounded ? 'Finishing up' : 'Fixing the answer'
    default:
      return 'Working'
  }
}

export type Verdict = 'verified' | 'unverified' | 'none'

export function verdictOf(steps: AgentStep[], answer: string): Verdict {
  const verifies = steps.filter((s) => s.node === 'verify' && !s.skipped)
  if (!verifies.length) return 'none'
  const grounded = verifies.at(-1)!.grounded === true
  return grounded && !answer.includes('⚠') ? 'verified' : 'unverified'
}

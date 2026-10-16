import type { Citation } from '../types'

const TOKEN = /([A-Za-z0-9&-]+) FY(\d{4}) p\.(\d+)/g
const BRACKET = /([ \t]*)\[([^[\]]*)\]/g

export const citeKey = (c: { ticker: string; fiscal_year: number; page: number }) =>
  `${c.ticker.toUpperCase()}-${c.fiscal_year}-${c.page}`

export interface Footnote {
  n: number
  key: string
  citation: Citation
}

/**
 * Turns "[BHIT FY2024 p.3]" (and grouped "[A p.1, B p.2]") into numbered markdown links
 * `[1](cite:1)` in order of first appearance, and returns the footnote list.
 */
export function linkifyCitations(answer: string, citations: Citation[]) {
  const byKey = new Map(citations.map((c) => [citeKey(c), c]))
  const order: Footnote[] = []
  const index = new Map<string, number>()

  const markdown = answer.replace(BRACKET, (whole, _gap: string, inner: string) => {
    if (![...inner.matchAll(TOKEN)].length) return whole
    const marker = (ticker: string, year: string, page: string) => {
      const key = `${ticker.toUpperCase()}-${year}-${page}`
      const citation = byKey.get(key)
      if (!citation) return ''
      if (!index.has(key)) {
        index.set(key, order.length + 1)
        order.push({ n: order.length + 1, key, citation })
      }
      return `[${index.get(key)}](cite:${key})`
    }
    const replaced = inner.replace(TOKEN, (_m, t: string, y: string, p: string) => marker(t, y, p))
    // a bracket that is only citations collapses to the markers; one with prose keeps its words
    const onlyCitations = inner.replace(TOKEN, '').replace(/[\s,;]+/g, '') === ''
    return onlyCitations ? replaced.replace(/\)\s+\[/g, ')[') : ` ${replaced}`
  })
  return { markdown, footnotes: order }
}

/** Numbers worth highlighting in a source passage (3+ digits, commas allowed). */
export function figuresIn(text: string): Set<string> {
  const stripped = text.replace(TOKEN, ' ')
  const out = new Set<string>()
  for (const m of stripped.matchAll(/\d+(?:,\d+)*(?:\.\d+)?/g)) {
    const digits = m[0].replace(/[,.]/g, '')
    const isYear = /^(19|20)\d{2}$/.test(m[0])
    if (digits.length >= 3 && !isYear) out.add(m[0])
  }
  return out
}

/** The PDF's own text can contain characters no extractor can decode (a broken font): show them as a marker. */
export const hasUnreadable = (text: string) => text.includes('\uFFFD')
/** Bold spans the extractor split badly, like `**Y **`, would print literal asterisks: move the spaces outside. */
const balanceBold = (text: string) =>
  text.replace(/\*\*([^*|\n]*?)\*\*/g, (_m, inner: string) => {
    const core = inner.trim()
    return core ? `${inner.slice(0, inner.length - inner.trimStart().length)}**${core}**${inner.slice(inner.trimEnd().length)}` : inner
  })

export const cleanUnreadable = (text: string) =>
  balanceBold(text)
    // some PDF fonts give the rupee sign as a backtick right before an amount: "` 27,14,715" -> "₹ 27,14,715"
    .replace(/(^|[\s(])`\s?(?=\d)/g, '$1₹ ')
    // a table cell with nothing readable in it (e.g. a lost year heading) becomes a dash
    .replace(/\|(\s*)(\*\*)?\s*(?:\uFFFD\s*)+(\*\*)?(\s*)(?=\|)/g, '|$1—$4')
    // partly readable text keeps a small marker where characters are missing
    .replace(/\uFFFD+/g, '▯')

const SENTENCE_BREAK = /(?<=[.!?])\s+(?=[A-Z0-9₹`])/

/**
 * A short quote from a prose passage: the sentence holding a figure from the answer, plus the one after it. Passages that are tables (or have no matching figure) are returned as null,
 * because a table row without its header says little.
 */
export function excerptAround(text: string, figures: Set<string>): string | null {
  if (/^\s*\|/m.test(text) || figures.size === 0) return null
  const sentences = text.split(SENTENCE_BREAK).map((s) => s.trim()).filter(Boolean)
  const hit = sentences.findIndex((s) => [...figures].some((f) => s.includes(f)))
  if (hit < 0) return null
  const start = hit
  const end = Math.min(sentences.length, hit + 2)
  if (start === 0 && end === sentences.length) return null
  const quote = sentences.slice(start, end).join(' ')
  return `${start > 0 ? '… ' : ''}${quote}${end < sentences.length ? ' …' : ''}`
}

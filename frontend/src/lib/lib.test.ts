import { describe, expect, it } from 'vitest'
import type { AgentStep, Citation } from '../types'
import { figuresIn, linkifyCitations } from './citations'
import { verdictOf } from './steps'

const cite = (ticker: string, year: number, page: number): Citation => ({
  ticker,
  fiscal_year: year,
  page,
  text: `${ticker} ${year} p${page}`,
})

describe('linkifyCitations', () => {
  it('numbers sources in order of first appearance and hugs the preceding word', () => {
    const { markdown, footnotes } = linkifyCitations(
      'Revenue rose [BHIT FY2024 p.5]. Risks too [BHIT FY2024 p.4] [BHIT FY2024 p.5].',
      [cite('BHIT', 2024, 5), cite('BHIT', 2024, 4)],
    )
    expect(footnotes.map((f) => f.n)).toEqual([1, 2])
    expect(markdown).toBe('Revenue rose[1](cite:BHIT-2024-5). Risks too[2](cite:BHIT-2024-4)[1](cite:BHIT-2024-5).')
  })

  it('handles grouped brackets and drops citations the backend did not return', () => {
    const { markdown, footnotes } = linkifyCitations('x [A FY2023 p.1, B FY2023 p.2, C FY2023 p.9]', [
      cite('A', 2023, 1),
      cite('B', 2023, 2),
    ])
    expect(footnotes).toHaveLength(2)
    expect(markdown).not.toContain('C-2023')
  })

  it('leaves ordinary brackets alone', () => {
    expect(linkifyCitations('see [note] and [1]', []).markdown).toBe('see [note] and [1]')
  })
})

describe('linkifyCitations edge cases', () => {
  it('works for tickers containing & or -', () => {
    const { footnotes } = linkifyCitations('x [M&M FY2024 p.3] y [BAJAJ-AUTO FY2023 p.9]', [cite('M&M', 2024, 3), cite('BAJAJ-AUTO', 2023, 9)])
    expect(footnotes.map((f) => f.key)).toEqual(['M&M-2024-3', 'BAJAJ-AUTO-2023-9'])
  })

  it('does not glue a citation onto the previous paragraph', () => {
    const { markdown } = linkifyCitations('First paragraph.\n\n[A FY2024 p.1] starts the next.', [cite('A', 2024, 1)])
    expect(markdown.startsWith('First paragraph.\n\n[1]')).toBe(true)
  })

  it('keeps the words of a bracket that mixes prose and a citation', () => {
    const { markdown } = linkifyCitations('see [BHIT FY2024 p.5 for details] now', [cite('BHIT', 2024, 5)])
    expect(markdown).toContain('for details')
    expect(markdown).toContain('(cite:BHIT-2024-5)')
  })
})

describe('figuresIn', () => {
  it('keeps real figures and ignores years and tiny numbers', () => {
    const f = figuresIn('In FY2024 revenue was Rs 1,89,866 crore, up 8.6% [BHIT FY2024 p.5] over 3 years')
    expect(f.has('1,89,866')).toBe(true)
    expect(f.has('2024')).toBe(false)
    expect(f.has('8.6')).toBe(false)
    expect(f.has('3')).toBe(false)
  })

  it('does not swallow a trailing comma into the figure', () => {
    expect(figuresIn('Revenue of 1,89,866, up 5%').has('1,89,866')).toBe(true)
  })
})

describe('verdictOf', () => {
  const verify = (grounded: boolean): AgentStep => ({ node: 'verify', grounded })
  it('is verified only when the backend check passed and no warning is in the text', () => {
    expect(verdictOf([verify(true)], 'fine')).toBe('verified')
    expect(verdictOf([verify(false)], 'fine')).toBe('unverified')
    expect(verdictOf([verify(true)], 'text ⚠ warning')).toBe('unverified')
    expect(verdictOf([], 'fine')).toBe('none')
  })
})

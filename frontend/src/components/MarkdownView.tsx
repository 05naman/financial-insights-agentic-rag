import { Children, cloneElement, isValidElement } from 'react'
import type { ReactElement, ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cleanUnreadable } from '../lib/citations'

const NUMBER = /(\d+(?:,\d+)*(?:\.\d+)?)/g
const NUMERIC_CELL = /^[\s(₹]*-?[\d,.]+%?\)?\s*$|^[-–—]$/

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children)
  return ''
}

function mark(node: ReactNode, figures: Set<string>): ReactNode {
  if (typeof node === 'string') {
    return node.split(NUMBER).map((part, i) =>
      figures.has(part) ? (
        <mark key={i} className="rounded bg-accent/25 px-0.5 text-inherit">
          {part}
        </mark>
      ) : (
        part
      ),
    )
  }
  if (Array.isArray(node)) return Children.map(node, (n) => mark(n, figures))
  if (isValidElement(node)) {
    const el = node as ReactElement<{ children?: ReactNode }>
    return cloneElement(el, undefined, mark(el.props.children, figures))
  }
  return node
}

interface Props {
  markdown: string
  variant: 'note' | 'passage'
  onCite?: (key: string) => void
  activeKey?: string | null
  highlight?: Set<string>
}

export default function MarkdownView({ markdown, variant, onCite, activeKey, highlight }: Props) {
  const wrap = (children: ReactNode) => (highlight?.size ? mark(children, highlight) : children)
  const small = variant === 'passage'

  const components: Components = {
    a({ href, children }) {
      if (href?.startsWith('cite:')) {
        const key = href.slice(5)
        const active = key === activeKey
        return (
          <sup className="mx-[1px] align-baseline leading-none">
            <button
              type="button"
              onClick={() => onCite?.(key)}
              aria-label={`Open source ${textOf(children)}`}
              className={`num inline-block -translate-y-[0.1em] rounded-[5px] px-[5px] py-[1px] text-[0.68rem] font-medium leading-[1.3] transition duration-150 active:scale-90 ${
                active
                  ? 'bg-accent text-bg'
                  : 'bg-accent-soft text-accent-ink hover:bg-accent hover:text-bg'
              }`}
            >
              {children}
            </button>
          </sup>
        )
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="underline decoration-line-strong underline-offset-2">
          {children}
        </a>
      )
    },
    table: ({ children }) => (
      <div
        className={`scroll-hint my-4 overflow-x-auto rounded-lg border border-line bg-surface ${
          small ? 'text-[0.78rem]' : ''
        }`}
      >
        <table className="w-full border-collapse font-sans text-[0.88rem] leading-snug [font-size:inherit]">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => <thead className="border-b border-line-strong">{children}</thead>,
    th: ({ children }) => (
      <th
        className={`text-left text-[0.7rem] font-semibold uppercase tracking-wider text-muted [&:not(:first-child)]:text-right ${
          small ? 'px-2 py-1.5' : 'px-3 py-2'
        }`}
      >
        {wrap(children)}
      </th>
    ),
    td: ({ children }) => {
      const numeric = NUMERIC_CELL.test(textOf(children).trim())
      return (
        <td
          className={`border-t border-line align-top ${small ? 'px-2 py-1' : 'px-3 py-1.5'} ${
            numeric ? 'num whitespace-nowrap text-right' : ''
          }`}
        >
          {wrap(children)}
        </td>
      )
    },
    p: ({ children }) => <p>{wrap(children)}</p>,
    li: ({ children }) => <li>{wrap(children)}</li>,
  }

  return (
    <div className={small ? 'font-sans text-[0.85rem] leading-relaxed [&_p]:my-2 [&_h1]:mt-3 [&_h2]:mt-3 [&_h1]:font-semibold [&_h2]:font-semibold' : 'note-prose'}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} disallowedElements={['img']} // a remote image would let injected text leak data via its URL
        urlTransform={(u) => (/^(cite:|https:|mailto:)/i.test(u) ? u : '')}>
        {cleanUnreadable(markdown).replace(/<br\s*\/?>/gi, ' ')}
      </ReactMarkdown>
    </div>
  )
}

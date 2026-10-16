import { useState } from 'react'
import type { ReactNode } from 'react'
import { AlertIcon, CheckIcon, CloseIcon } from '../components/Icons'
import Button from './Button'
import IconButton from './IconButton'

type Kind = 'error' | 'success' | 'info' | 'warning'

const STYLE: Record<Kind, string> = {
  error: 'border-danger/30 bg-danger-soft text-danger',
  success: 'border-primary/30 bg-primary-soft text-primary',
  info: 'border-line-strong bg-surface text-muted',
  warning: 'border-accent/40 bg-accent-soft text-accent-ink',
}

interface Props {
  kind?: Kind
  title?: string
  children?: ReactNode
  /** Shows a "Try again" button; may return a promise to show its loading state. */
  onRetry?: () => void | Promise<unknown>
  onDismiss?: () => void
  className?: string
}

export default function Alert({ kind = 'error', title, children, onRetry, onDismiss, className = '' }: Props) {
  const [retrying, setRetrying] = useState(false)

  async function retry() {
    setRetrying(true)
    try {
      await onRetry?.()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-3 rounded-lg border p-3.5 text-sm ${STYLE[kind]} ${className}`}
    >
      {kind === 'success' ? (
        <CheckIcon width={18} height={18} className="mt-0.5 shrink-0" />
      ) : (
        <AlertIcon width={18} height={18} className="mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={title ? 'mt-0.5 text-ink/80' : ''}>{children}</div>}
        {onRetry && (
          <Button size="sm" variant="ink" className="mt-3" loading={retrying} loadingText="Trying…" onClick={retry}>
            Try again
          </Button>
        )}
      </div>
      {onDismiss && (
        <IconButton label="Dismiss" size="sm" className="-mr-1 -mt-1 text-current" onClick={onDismiss}>
          <CloseIcon width={14} height={14} />
        </IconButton>
      )}
    </div>
  )
}

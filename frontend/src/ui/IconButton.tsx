import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import Spinner from './Spinner'

type Variant = 'ghost' | 'outline' | 'primary' | 'ink' | 'danger'
type Size = 'sm' | 'md'

const VARIANT: Record<Variant, string> = {
  ghost: 'text-muted hover:bg-line/70 hover:text-ink active:bg-line',
  outline: 'border border-line-strong text-ink hover:bg-line/60 active:bg-line',
  primary: 'bg-primary text-primary-ink hover:brightness-110 active:brightness-95',
  ink: 'bg-ink text-bg hover:opacity-90 active:opacity-80',
  danger: 'text-faint hover:bg-danger-soft hover:text-danger active:bg-danger/20',
}
const SIZE: Record<Size, string> = { sm: 'size-7', md: 'size-9' }

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  /** Required: icon-only buttons need an accessible name (also shown as the tooltip). */
  label: string
  variant?: Variant
  size?: Size
  loading?: boolean
  children: ReactNode
}

const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, variant = 'ghost', size = 'md', loading = false, disabled, className = '', children, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`grid shrink-0 place-items-center rounded-full transition duration-150 ease-out active:scale-95 disabled:pointer-events-none disabled:opacity-40 aria-busy:cursor-progress ${SIZE[size]} ${VARIANT[variant]} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : children}
    </button>
  )
})
export default IconButton

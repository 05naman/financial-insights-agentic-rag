import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import Spinner from './Spinner'

export type ButtonVariant = 'primary' | 'ink' | 'secondary' | 'ghost' | 'danger' | 'danger-soft' | 'link'
type Size = 'sm' | 'md' | 'lg'

/**
 * Every state is defined here once: rest, hover, pressed (active), keyboard focus (global ring),
 * disabled, and loading (spinner + aria-busy, blocks double-submits, keeps its width).
 */
const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-ink hover:brightness-110 active:brightness-95',
  ink: 'bg-ink text-bg hover:opacity-90 active:opacity-80',
  secondary:
    'border border-line-strong bg-raised text-ink shadow-card hover:border-primary hover:bg-primary-soft active:bg-primary-soft/60',
  ghost: 'text-muted hover:bg-line/60 hover:text-ink active:bg-line',
  danger: 'bg-danger text-white hover:brightness-110 active:brightness-95',
  'danger-soft': 'bg-danger-soft text-danger hover:bg-danger/15 active:bg-danger/25',
  link: 'h-auto rounded-sm px-0 text-primary underline decoration-primary/30 underline-offset-4 hover:decoration-primary active:opacity-70',
}
const SIZE: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-[0.95rem]',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: Size
  loading?: boolean
  loadingText?: string
  leftIcon?: ReactNode
  fullWidth?: boolean
}

const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = 'primary', size = 'md', loading = false, loadingText, leftIcon, fullWidth, disabled, className = '', children, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition duration-150 ease-out active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 aria-busy:cursor-progress aria-busy:opacity-80 ${
        VARIANT[variant]
      } ${variant === 'link' ? '' : SIZE[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {loading && loadingText ? loadingText : children}
    </button>
  )
})
export default Button

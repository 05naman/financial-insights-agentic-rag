export default function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  )
}

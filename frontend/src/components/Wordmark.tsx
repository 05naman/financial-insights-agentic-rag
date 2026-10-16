export default function Wordmark({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const lg = size === 'lg'
  return (
    <div className="flex items-center gap-2.5">
      <svg width={lg ? 30 : 24} height={lg ? 30 : 24} viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" fill="var(--primary)" />
        <rect x="7" y="9" width="18" height="2.4" rx="1.2" fill="var(--primary-ink)" />
        <rect x="7" y="14.8" width="12" height="2.4" rx="1.2" fill="var(--primary-ink)" />
        <rect x="7" y="20.6" width="15" height="2.4" rx="1.2" fill="var(--accent)" />
      </svg>
      <span className={`font-serif font-semibold leading-none tracking-tight ${lg ? 'text-2xl' : 'text-[1.15rem]'}`}>
        Financial Insights
      </span>
    </div>
  )
}

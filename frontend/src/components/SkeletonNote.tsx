/** Shaped like a finished answer: a lead paragraph, a small table, then a closing line. */
export default function SkeletonNote() {
  return (
    <div className="space-y-5" aria-hidden>
      <div className="space-y-2.5">
        <div className="skeleton h-4 w-[92%]" />
        <div className="skeleton h-4 w-[78%]" />
      </div>
      <div className="overflow-hidden rounded-lg border border-line">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`flex gap-6 px-3 py-2.5 ${i ? 'border-t border-line' : ''}`}>
            <div className="skeleton h-3.5 w-1/2" />
            <div className="skeleton ml-auto h-3.5 w-16" />
            <div className="skeleton h-3.5 w-16" />
          </div>
        ))}
      </div>
      <div className="skeleton h-4 w-[64%]" />
    </div>
  )
}

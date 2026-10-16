import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="grid h-full min-h-[60dvh] place-items-center px-6 text-center">
      <div>
        <p className="num text-sm text-faint">404</p>
        <h1 className="mt-1 font-serif text-4xl font-medium tracking-tight">Page not found</h1>
        <p className="mt-2 text-muted">That page doesn't exist, or it moved.</p>
        <Link
          to="/"
          className="mt-6 inline-flex h-10 items-center rounded-lg bg-ink px-4 text-sm font-medium text-bg transition duration-150 hover:opacity-90 active:scale-[0.98] active:opacity-80"
        >
          Back to questions
        </Link>
      </div>
    </div>
  )
}

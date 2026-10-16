import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import Button from './Button'

interface Props {
  children: ReactNode
  /** Smaller inline fallback (for a section) instead of a full-page one. */
  inline?: boolean
}
interface State {
  error: Error | null
}

/** Catches render-time crashes so one bad component never leaves a blank white page. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    const box = (
      <div role="alert" className="mx-auto max-w-md p-6 text-center">
        <h2 className="font-serif text-2xl font-medium">Something broke on this screen</h2>
        <p className="mt-2 text-sm text-muted">
          Your data is safe. Reloading usually fixes it; if it keeps happening, try signing out and back in.
        </p>
        {import.meta.env.DEV && (
          <pre className="mt-3 max-h-32 overflow-auto rounded-md bg-danger-soft p-2 text-left text-xs text-danger">
            {this.state.error.message}
          </pre>
        )}
        <div className="mt-5 flex justify-center gap-2">
          <Button onClick={() => window.location.reload()}>Reload</Button>
          <Button variant="secondary" onClick={() => this.setState({ error: null })}>
            Dismiss
          </Button>
        </div>
      </div>
    )
    return this.props.inline ? box : <div className="grid min-h-dvh place-items-center bg-bg text-ink">{box}</div>
  }
}

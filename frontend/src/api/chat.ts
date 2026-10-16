import type { AgentStep, ChatMessage, FinalAnswer, Mode, Session } from '../types'
import { ApiError, UNAUTHORIZED_EVENT, apiUrl, errorFromResponse, networkError, request, tokenStore } from './client'

export const listSessions = () => request<Session[]>('/chat/sessions')
export const createSession = (signal?: AbortSignal) =>
  request<Session>('/chat/sessions', { method: 'POST' }, { signal })
export const deleteSession = (id: number) => request<void>(`/chat/sessions/${id}`, { method: 'DELETE' })
export const getMessages = (id: number) => request<ChatMessage[]>(`/chat/sessions/${id}/messages`)

interface StreamHandlers {
  onStep: (step: AgentStep) => void
  onFinal: (answer: FinalAnswer) => void
}

const IDLE_TIMEOUT_MS = 120_000 // no bytes at all for this long means the connection is dead

/** POST + Server-Sent Events (EventSource can't send POST bodies or auth headers). */
export async function streamAnswer(
  sessionId: number,
  question: string,
  mode: Mode,
  { onStep, onFinal }: StreamHandlers,
  signal?: AbortSignal,
) {
  const controller = new AbortController()
  let idle = false
  let idleTimer: ReturnType<typeof setTimeout> | undefined
  const bump = () => {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      idle = true
      controller.abort()
    }, IDLE_TIMEOUT_MS)
  }
  const onAbort = () => controller.abort()
  signal?.addEventListener('abort', onAbort)
  if (signal?.aborted) controller.abort() // Stop was pressed before we started listening
  bump()

  try {
    if (signal?.aborted) throw new ApiError('aborted', 'Stopped.')
    let res: Response
    try {
      res = await fetch(apiUrl(`/chat/sessions/${sessionId}/stream`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenStore.get() ?? ''}` },
        body: JSON.stringify({ question, mode }),
        signal: controller.signal,
      })
    } catch {
      if (signal?.aborted) throw new ApiError('aborted', 'Stopped.')
      if (idle) throw new ApiError('timeout', 'The server took too long to respond. Please try again.')
      throw networkError()
    }
    if (!res.ok || !res.body) {
      const err = await errorFromResponse(res)
      if (err.kind === 'unauthorized') {
        tokenStore.clear()
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
      }
      throw err
    }

    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    let gotFinal = false
    for (;;) {
      let chunk: ReadableStreamReadResult<string>
      try {
        chunk = await reader.read()
      } catch {
        if (signal?.aborted) throw new ApiError('aborted', 'Stopped.')
        if (idle) throw new ApiError('timeout', 'The answer stopped arriving. Please try again.')
        throw new ApiError('network', 'The connection was lost while answering. Please try again.')
      }
      if (chunk.done) break
      bump()
      buffer = (buffer + chunk.value).replace(/\r\n?/g, '\n') // tolerate CRLF framing from proxies
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const event = /^event: ?(.*)$/m.exec(block)?.[1]?.trim()
        const data = [...block.matchAll(/^data: ?(.*)$/gm)].map((m) => m[1]).join('\n') // multi-line data
        if (!event || !data) continue
        let payload: unknown
        try {
          payload = JSON.parse(data)
        } catch {
          continue // ignore a malformed event rather than failing the whole answer
        }
        if (event === 'step') onStep(payload as AgentStep)
        else if (event === 'final') {
          gotFinal = true
          onFinal(payload as FinalAnswer)
        } else if (event === 'error') {
          const detail = (payload as { detail?: string }).detail
          throw new ApiError('server', detail || 'Something went wrong while answering. Please try again.')
        }
      }
    }
    if (!gotFinal) throw new ApiError('network', 'The answer stream ended unexpectedly. Please try again.')
  } finally {
    clearTimeout(idleTimer)
    signal?.removeEventListener('abort', onAbort)
    controller.abort() // closes the connection if we are leaving early (error event, parse failure)
  }
}

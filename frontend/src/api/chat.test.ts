import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentStep, FinalAnswer } from '../types'
import { streamAnswer } from './chat'
import { ApiError } from './client'

/** A fetch Response whose body arrives in the exact pieces given (to test events split across chunks). */
function sse(chunks: string[], status = 200) {
  const enc = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)))
      c.close()
    },
  })
  return new Response(body, { status, headers: { 'content-type': 'text/event-stream' } })
}

async function run(chunks: string[], signal?: AbortSignal) {
  const steps: AgentStep[] = []
  const finals: FinalAnswer[] = []
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(sse(chunks))
  const done = streamAnswer(1, 'q?', 'agentic', { onStep: (s) => steps.push(s), onFinal: (f) => finals.push(f) }, signal)
  return { steps, finals, done }
}

const step = 'event: step\ndata: {"node":"plan"}\n\n'
const final = 'event: final\ndata: {"answer":"A","citations":[],"steps":[],"llm_calls":1,"mode":"agentic"}\n\n'

afterEach(() => vi.restoreAllMocks())

describe('streamAnswer', () => {
  it('assembles events that are split across network chunks', async () => {
    const whole = step + final
    const { steps, finals, done } = await run([whole.slice(0, 17), whole.slice(17, 60), whole.slice(60)])
    await done
    expect(steps).toHaveLength(1)
    expect(finals[0].answer).toBe('A')
  })

  it('accepts CRLF framing and "data:" without a space', async () => {
    const crlf = 'event: step\r\ndata:{"node":"plan"}\r\n\r\n' + final.replace(/\n/g, '\r\n')
    const { steps, finals, done } = await run([crlf])
    await done
    expect(steps).toHaveLength(1)
    expect(finals).toHaveLength(1)
  })

  it('joins multi-line data fields', async () => {
    const multi = 'event: final\ndata: {"answer":"A",\ndata: "citations":[],"steps":[],"llm_calls":1,"mode":"agentic"}\n\n'
    const { finals, done } = await run([multi])
    await done
    expect(finals[0].answer).toBe('A')
  })

  it('ignores a malformed event instead of failing the whole answer', async () => {
    const { finals, done } = await run(['event: step\ndata: {oops\n\n' + final])
    await done
    expect(finals).toHaveLength(1)
  })

  it('reports a stream that ends without an answer', async () => {
    const { done } = await run([step])
    await expect(done).rejects.toMatchObject({ kind: 'network' })
  })

  it('turns a server error event into an ApiError', async () => {
    const { done } = await run(['event: error\ndata: {"detail":"Nope, try later"}\n\n'])
    await expect(done).rejects.toThrow('Nope, try later')
  })

  it('stops immediately if Stop was already pressed', async () => {
    const c = new AbortController()
    c.abort()
    const spy = vi.spyOn(globalThis, 'fetch')
    await expect(streamAnswer(1, 'q', 'agentic', { onStep() {}, onFinal() {} }, c.signal)).rejects.toBeInstanceOf(ApiError)
    expect(spy).not.toHaveBeenCalled()
  })
})

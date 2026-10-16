import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as chatApi from '../api/chat'
import { ApiError, describeError, isAborted } from '../api/client'
import Composer from '../components/Composer'
import EmptyState from '../components/EmptyState'
import EvidencePane from '../components/EvidencePane'
import NoteView from '../components/NoteView'
import type { Note } from '../components/NoteView'
import { useSessions } from '../context/SessionsContext'
import { useDocuments } from '../hooks/useDocuments'
import { linkifyCitations } from '../lib/citations'
import type { ChatMessage, Mode } from '../types'
import Alert from '../ui/Alert'
import { useToast } from '../ui/Toast'

let noteCounter = 0
const nextId = () => `n${++noteCounter}`

/** Stored messages come as a flat list; fold them into question/answer notes. */
function toNotes(messages: ChatMessage[]): Note[] {
  const notes: Note[] = []
  for (const m of messages) {
    if (m.role === 'user') {
      const prev = notes[notes.length - 1]
      if (prev && !prev.message && prev.question === m.content) notes.pop() // a retried, never-answered copy
      notes.push({ id: nextId(), question: m.content, status: 'error', steps: [], error: 'No answer was saved for this question.' })
    } else if (notes.length) {
      const last = notes[notes.length - 1]
      last.message = m
      last.status = 'done'
      last.error = undefined
    }
  }
  return notes
}

function SkeletonThread() {
  return (
    <div className="space-y-6 pt-2" aria-hidden>
      <div className="skeleton h-8 w-3/4" />
      <div className="space-y-2.5">
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-[88%]" />
        <div className="skeleton h-4 w-[70%]" />
      </div>
    </div>
  )
}

export default function AskPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { refresh } = useSessions()
  const toast = useToast()
  const { docs, loading: docsLoading, error: docsError, refresh: refreshDocs } = useDocuments()

  const [notes, setNotes] = useState<Note[]>([])
  const [loadingThread, setLoadingThread] = useState(false)
  const [threadError, setThreadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [text, setText] = useState('')
  const [mode, setMode] = useState<Mode>('agentic')
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<{ noteId: string; key: string } | null>(null)
  const [wide, setWide] = useState(false)

  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const ownSession = useRef<number | null>(null) // a session this page just created: don't reload it

  const id = sessionId && /^\d+$/.test(sessionId) ? Number(sessionId) : null

  // load a stored thread when the URL points at one
  useEffect(() => {
    setSelected(null)
    setThreadError(null)
    // we just created this chat ourselves and navigated to it: nothing to load (and forget the flag,
    // otherwise opening this chat again later would wrongly skip the load)
    if (ownSession.current !== null && ownSession.current === id) {
      ownSession.current = null
      return
    }
    // the user moved to a different conversation: stop any answer still streaming for the old one
    abortRef.current?.abort()
    if (id === null) {
      setNotes([])
      setLoadingThread(false)
      return
    }
    let cancelled = false
    setLoadingThread(true)
    chatApi
      .getMessages(id)
      .then((m) => !cancelled && setNotes(toNotes(m)))
      .catch((e) => {
        if (cancelled) return
        if (e instanceof ApiError && e.kind === 'not_found') {
          toast.error('That question no longer exists.')
          navigate('/', { replace: true })
        } else {
          setNotes([])
          setThreadError(describeError(e, "Couldn't load this conversation."))
        }
      })
      .finally(() => !cancelled && setLoadingThread(false))
    return () => {
      cancelled = true
      setLoadingThread(false) // never leave the skeleton stuck when the user navigates mid-load
    }
  }, [id, navigate, toast, reloadKey])

  // leaving the page also stops a running answer
  useEffect(() => () => abortRef.current?.abort(), [])

  // bring the newest question to the top of the view (so you read from the start of the answer)
  const lastNoteId = notes.at(-1)?.id
  useEffect(() => {
    if (!lastNoteId) return
    const el = scrollRef.current?.querySelector<HTMLElement>(`[data-note-id="${lastNoteId}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [lastNoteId])

  const patch = useCallback((noteId: string, change: Partial<Note>) => {
    setNotes((all) => all.map((n) => (n.id === noteId ? { ...n, ...change } : n)))
  }, [])

  const ask = useCallback(
    async (question: string, retryNoteId?: string) => {
      const q = question.trim()
      if (q.length < 3 || busy) return
      setBusy(true)
      if (!retryNoteId) setText('')
      const noteId = retryNoteId ?? nextId()
      const fresh: Note = { id: noteId, question: q, status: 'loading', steps: [] }
      setNotes((all) => (retryNoteId ? all.map((n) => (n.id === noteId ? fresh : n)) : [...all, fresh]))

      const controller = new AbortController()
      abortRef.current = controller
      let createdHere: number | null = null
      let committed = false
      // Move to /<id> only once the server has started answering, so a request that fails up front
      // keeps its error on screen instead of being wiped by a navigation.
      const commit = () => {
        if (committed || createdHere === null || controller.signal.aborted) return
        committed = true
        navigate(`/${createdHere}`, { replace: true })
      }
      try {
        let sid = id
        if (sid === null) {
          sid = (await chatApi.createSession(controller.signal)).id
          ownSession.current = sid
          createdHere = sid
        }
        await chatApi.streamAnswer(
          sid,
          q,
          mode,
          {
            onStep: (step) => {
              commit()
              setNotes((all) => all.map((n) => (n.id === noteId ? { ...n, steps: [...n.steps, step] } : n)))
            },
            onFinal: (a) => {
              commit()
              patch(noteId, {
                status: 'done',
                message: { role: 'assistant', content: a.answer, citations: a.citations, steps: a.steps },
              })
            },
          },
          controller.signal,
        )
        refresh()
      } catch (e) {
        const stopped = controller.signal.aborted || isAborted(e)
        patch(noteId, {
          status: 'error',
          error: stopped ? 'Stopped before the answer finished.' : describeError(e, 'Request failed'),
        })
        // nothing reached the server: remove the empty chat we just created (the error stays visible)
        if (createdHere !== null && !committed) {
          chatApi.deleteSession(createdHere).then(refresh).catch(() => {})
          ownSession.current = null
        }
      } finally {
        setBusy(false)
        abortRef.current = null
        if (committed) refresh() // the chat exists server-side even if the answer was stopped or failed
      }
    },
    [busy, id, mode, navigate, patch, refresh],
  )

  const selectedNote = notes.find((n) => n.id === selected?.noteId)
  const footnotes = useMemo(
    () => (selectedNote?.message ? linkifyCitations(selectedNote.message.content, selectedNote.message.citations).footnotes : []),
    [selectedNote],
  )
  const showEmpty = notes.length === 0 && !loadingThread && !threadError

  return (
    <div className="flex h-full">
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[720px] px-5 pb-48 pt-6 sm:px-8 sm:pt-10">
            {loadingThread && <SkeletonThread />}
            {threadError && (
              <Alert kind="error" title="Couldn't open this conversation" onRetry={() => setReloadKey((k) => k + 1)}>
                {threadError}
              </Alert>
            )}
            {showEmpty && (
              <EmptyState
                docs={docs}
                loading={docsLoading}
                error={docsError}
                onRetry={refreshDocs}
                disabled={busy}
                onPick={(q) => {
                  setText(q)
                  ask(q)
                }}
              />
            )}
            {notes.map((n) => (
              <NoteView
                key={n.id}
                note={n}
                activeKey={selected?.noteId === n.id ? selected.key : null}
                onCite={(noteId, key) => setSelected({ noteId, key })}
                onRetry={(note) => ask(note.question, note.id)}
              />
            ))}
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-bg via-bg/95 to-transparent pt-12">
          <div className="pointer-events-auto mx-auto max-w-[720px] px-5 pb-5 sm:px-8">
            <Composer
              value={text}
              onChange={setText}
              onSubmit={() => ask(text)}
              onStop={() => abortRef.current?.abort()}
              busy={busy}
              mode={mode}
              onMode={setMode}
              inputRef={inputRef}
            />
            <p className="mt-2 text-center text-[0.7rem] text-faint">
              Research information from annual reports, not investment advice. Always check the cited page.
            </p>
          </div>
        </div>
      </div>

      {selected && footnotes.length > 0 && selectedNote?.message && (
        <>
          <button
            aria-label="Close evidence"
            className="fixed inset-0 z-30 bg-ink/40 lg:hidden"
            onClick={() => setSelected(null)}
          />
          <div className={`fixed inset-y-0 right-0 z-40 w-[min(92vw,440px)] lg:static lg:z-auto lg:shrink-0 ${
              wide ? 'lg:w-[min(62vw,980px)]' : 'lg:w-[420px] xl:w-[560px]'
            }`}>
            <EvidencePane
              footnotes={footnotes}
              activeKey={selected.key}
              answer={selectedNote.message.content}
              onSelect={(key) => setSelected({ noteId: selected.noteId, key })}
              onClose={() => setSelected(null)}
              expanded={wide}
              onToggleExpand={() => setWide((w) => !w)}
            />
          </div>
        </>
      )}
    </div>
  )
}

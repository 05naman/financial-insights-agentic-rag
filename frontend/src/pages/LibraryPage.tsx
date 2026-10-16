import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { describeError } from '../api/client'
import { MAX_UPLOAD_MB, deleteDocument, uploadDocument } from '../api/documents'
import CoverageGrid from '../components/CoverageGrid'
import { TrashIcon, UploadIcon } from '../components/Icons'
import { useDocuments } from '../hooks/useDocuments'
import type { DocumentInfo } from '../types'
import Alert from '../ui/Alert'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'
import { useToast } from '../ui/Toast'

const NAME_OK = /^[A-Za-z0-9&-]+_FY\d{4}\.pdf$/i

const pill: Record<DocumentInfo['status'], string> = {
  ready: 'bg-primary-soft text-primary',
  processing: 'bg-accent-soft text-accent-ink',
  pending: 'bg-line text-muted',
  failed: 'bg-danger-soft text-danger',
}
const label: Record<DocumentInfo['status'], string> = {
  ready: 'Ready',
  processing: 'Reading pages',
  pending: 'Queued',
  failed: 'Failed',
}

/** Returns a reason the file can't be uploaded, or null. Cheap checks run before any network call. */
function rejectReason(f: File): string | null {
  if (!f.name.toLowerCase().endsWith('.pdf') && f.type !== 'application/pdf') return `${f.name} is not a PDF.`
  if (!NAME_OK.test(f.name)) return `Rename ${f.name} to TICKER_FYyyyy.pdf (for example TCS_FY2024.pdf).`
  if (f.size === 0) return `${f.name} is empty.`
  if (f.size > MAX_UPLOAD_MB * 1024 * 1024) return `${f.name} is larger than ${MAX_UPLOAD_MB} MB.`
  return null
}

export default function LibraryPage() {
  const { docs, loading, error, refresh, working } = useDocuments()
  const toast = useToast()
  const [dragging, setDragging] = useState(false)
  const [sending, setSending] = useState<string[]>([])
  const [confirming, setConfirming] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)

  async function uploadOne(f: File) {
    setSending((s) => [...s, f.name])
    try {
      await uploadDocument(f)
      toast.success(`${f.name} uploaded. Reading its pages now; a long report can take a few minutes.`)
    } catch (e) {
      toast.error(`${f.name}: ${describeError(e, 'upload failed')}`, { label: 'Retry', onClick: () => uploadOne(f) })
    } finally {
      setSending((s) => s.filter((n) => n !== f.name))
      setTimeout(refresh, 900)
    }
  }

  async function upload(files: File[]) {
    if (!files.length) return
    const ok: File[] = []
    for (const f of files) {
      const reason = rejectReason(f)
      if (reason) toast.error(reason)
      else ok.push(f)
    }
    for (const f of ok) await uploadOne(f)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    upload([...e.dataTransfer.files])
  }

  async function remove(d: DocumentInfo) {
    if (confirming !== d.id) {
      setConfirming(d.id)
      setTimeout(() => setConfirming((c) => (c === d.id ? null : c)), 3000)
      return
    }
    setDeleting(d.id)
    try {
      await deleteDocument(d.id)
      toast.success(`${d.ticker} FY${d.fiscal_year} removed.`)
      await refresh()
    } catch (e) {
      toast.error(`Couldn't remove ${d.ticker} FY${d.fiscal_year}. ${describeError(e)}`)
    } finally {
      setDeleting(null)
      setConfirming(null)
    }
  }

  const uploading = sending.length > 0
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[860px] px-5 py-8 sm:px-8 sm:py-12">
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">Library</p>
        <h1 className="mt-1 font-serif text-[2.2rem] font-medium leading-tight tracking-tight">Annual reports</h1>
        <p className="mt-2 max-w-[34rem] text-muted">
          The assistant answers only from the reports listed here. Add a PDF and it becomes searchable once its pages have
          been read.
        </p>

        {error && (
          <Alert kind="error" title="Couldn't refresh your reports" className="mt-6" onRetry={refresh}>
            {error}
            {docs.length > 0 && ' Showing the last list we loaded.'}
          </Alert>
        )}

        <section className="mt-8" aria-label="Coverage">
          <CoverageGrid docs={docs} loading={loading} />
        </section>

        <section
          aria-label="Add a report"
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false)
          }}
          onDrop={onDrop}
          className={`mt-8 rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
            dragging ? 'border-primary bg-primary-soft' : 'border-line-strong'
          }`}
        >
          <UploadIcon className="mx-auto text-muted" width={26} height={26} />
          <p className="mt-3 font-medium">{dragging ? 'Release to upload' : 'Drop PDFs here, or'}</p>
          <Button className="mt-2" variant="ink" loading={uploading} loadingText="Uploading…" onClick={() => input.current?.click()}>
            Choose files
          </Button>
          <input
            ref={input}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            onChange={(e) => {
              upload([...(e.target.files ?? [])])
              e.target.value = ''
            }}
          />
          <p className="mt-3 text-xs text-muted">
            Name files like <code className="num rounded bg-line px-1.5 py-0.5">TCS_FY2024.pdf</code> so the company and year
            are recognised. Up to {MAX_UPLOAD_MB} MB each.
          </p>
          {uploading && (
            <div className="mx-auto mt-5 max-w-sm space-y-2" role="status">
              {sending.map((n) => (
                <div key={n} className="text-left text-xs text-muted">
                  Uploading {n}
                  <div className="indeterminate mt-1 h-1 overflow-hidden rounded-full bg-line" />
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="mt-10" aria-label="All reports">
          <h2 className="mb-2 flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-faint">
            All reports {working && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" />}
          </h2>
          <div className="overflow-hidden rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[0.7rem] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2.5 font-semibold">Company</th>
                  <th className="px-4 py-2.5 font-semibold">Year</th>
                  <th className="hidden px-4 py-2.5 text-right font-semibold sm:table-cell">Pages</th>
                  <th className="hidden px-4 py-2.5 text-right font-semibold sm:table-cell">Passages</th>
                  <th className="px-4 py-2.5 font-semibold">Status</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody>
                {loading &&
                  [0, 1, 2].map((i) => (
                    <tr key={i} className="border-t border-line" aria-hidden>
                      <td colSpan={6} className="px-4 py-3">
                        <div className="skeleton h-5 w-full" />
                      </td>
                    </tr>
                  ))}
                {!loading &&
                  docs.map((d) => (
                    <tr key={d.id} className="rise border-t border-line first:border-t-0">
                      <td className="px-4 py-3 font-medium">{d.ticker}</td>
                      <td className="num px-4 py-3">FY{d.fiscal_year}</td>
                      <td className="num hidden px-4 py-3 text-right sm:table-cell">{d.page_count || '—'}</td>
                      <td className="num hidden px-4 py-3 text-right sm:table-cell">{d.chunk_count || '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${pill[d.status]}`}>
                          {d.status === 'processing' && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-current" />}
                          {label[d.status]}
                        </span>
                        {d.error && (
                          <span className="mt-1 block max-w-[16rem] truncate text-xs text-danger" title={d.error}>
                            {d.error}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right">
                        {confirming === d.id ? (
                          <Button size="sm" variant="danger-soft" loading={deleting === d.id} onClick={() => remove(d)}>
                            Delete?
                          </Button>
                        ) : (
                          <IconButton
                            label={`Delete ${d.ticker} FY${d.fiscal_year}`}
                            variant="danger"
                            size="sm"
                            disabled={d.status === 'processing'}
                            onClick={() => remove(d)}
                          >
                            <TrashIcon width={15} height={15} />
                          </IconButton>
                        )}
                      </td>
                    </tr>
                  ))}
                {!loading && docs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-muted">
                      Nothing here yet. Drop a report above to get started.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}

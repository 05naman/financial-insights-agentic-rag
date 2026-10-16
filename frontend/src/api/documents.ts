import type { DocumentInfo } from '../types'
import { request } from './client'

export const MAX_UPLOAD_MB = 100

export const listDocuments = () => request<DocumentInfo[]>('/documents')

export function uploadDocument(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request('/documents', { method: 'POST', body: form }, { timeoutMs: 180_000 })
}

export const deleteDocument = (id: number) => request<void>(`/documents/${id}`, { method: 'DELETE' })

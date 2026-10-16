export type Mode = 'naive' | 'hybrid' | 'agentic'

export interface Citation {
  ticker: string
  fiscal_year: number
  page: number
  text: string
}

export interface AgentStep {
  node: string
  [key: string]: unknown
}

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  steps: AgentStep[]
}

export interface Session {
  id: number
  title: string
  created_at: string
}

export interface DocumentInfo {
  id: number
  ticker: string
  fiscal_year: number
  filename: string
  page_count: number
  chunk_count: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error: string | null
}

export interface FinalAnswer {
  answer: string
  citations: Citation[]
  steps: AgentStep[]
  llm_calls: number
  mode: Mode
}

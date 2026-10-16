# Financial Insights: Agentic RAG for Indian Company Annual Reports

**Pitch:** An AI research assistant that answers complex questions about Indian listed companies from their annual report PDFs: it finds the right pages, compares figures across years, runs calculations, and cites the page for every claim. Adding a company means adding its PDFs, with no company-specific code.

**Example:** "How did TCS's revenue and operating margin change over the last 3 years, and what risks does it flag?"

**Goals:** (1) learn agentic RAG properly, (2) SDE-1 level full-stack project (FastAPI + React), (3) measurable results: naive RAG vs agentic RAG.

**Source decision:** annual report PDFs only, supplied by the user (local folder or upload). No scraping, no data APIs. The only external service is the LLM.

---

## Stack (all free)

| Layer | Choice |
|---|---|
| Backend | FastAPI (async, SSE streaming) |
| Agent | LangGraph |
| PDF parsing | PyMuPDF (text + table extraction) |
| Vector DB | Qdrant (embedded locally, server optional), dense + sparse BM25 hybrid |
| DB | SQLite default, PostgreSQL optional: users, chats, documents, ingestion jobs |
| Embeddings / sparse / reranker | fastembed (ONNX, local): `bge-small-en`, BM25, cross-encoder |
| LLM | Groq free tier (default), Gemini (fallback), Ollama (local), behind one provider interface |
| Evals | Custom question set and scoring script |
| Frontend | React + Vite + Tailwind (Vercel) |
| Ops | Docker Compose, GitHub Actions, pytest, ruff |

Backend, Qdrant and Postgres need a host other than Vercel (Render/Fly + Qdrant Cloud free tier).

---

## Architecture (layers)

```
api/         HTTP routes + request/response schemas (thin)
services/    business logic: chat, documents, ingestion orchestration
agent/       LangGraph: state, nodes, tools, prompts, graph
retrieval/   embedder, vector store, hybrid search, reranker
ingestion/   pdf loader, table-aware chunker, pipeline
llm/         provider interface + fallback
db/          models, session, repositories
core/        config, logging, security, errors
```
Rules: routes call services, services call repositories and agent, nothing imports upward.

---

## Scope

**MVP:** ingest PDFs, hybrid retrieval with reranking, agent loop with calculator, page-cited answers, chat API, simple UI, eval report.
**Later:** auth, chat history, agent-steps panel, deploy.
**Out of scope:** investment advice, live market data, scraping.

Start with 3-5 companies (e.g. TCS, Infosys, Reliance), 3 years each. File naming: `data/pdfs/TICKER_FYyyyy.pdf`.

---

## Phases

### Phase 0: Setup (done)
- [x] FastAPI skeleton, config, logging, ruff, pytest
- [x] LLM provider interface with fallback
- [x] Docker Compose (Postgres, Qdrant; optional)

### Phase 1: Ingestion (done; validated on real TCS, Infosys, HDFC Bank reports)
- [x] PDF loader: per-page text and tables (tables as markdown)
- [x] Parse company and fiscal year from file name
- [x] Chunker: page-aware, tables kept whole, with metadata (company, year, page, type)
- [x] Embed (dense + sparse) and upsert into Qdrant
- [x] `documents` table and ingestion status
- [x] CLI `ingest --dir data/pdfs` and upload endpoint

**Done when:** a PDF is searchable and each hit knows its company, year and page.

### Phase 2: Naive RAG baseline (done)
- [x] `/ask`: dense top-k, then LLM answers with citations
- [x] Eval set: 40-60 questions (single fact, multi-year comparison, multi-company, risks, unanswerable) with expected answers
- [x] Eval script: accuracy, citation correctness, groundedness
- [x] **Record baseline numbers**

### Phase 3: Better retrieval
- [x] Hybrid (dense + BM25) with rank fusion
- [x] Cross-encoder reranker
- [x] Metadata filters (company, year)
- [x] Re-run evals and log the gain per step

### Phase 4: Agentic layer (core)
- [x] Planner: decompose into sub-questions with company/year filters
- [x] Tools: `search_reports`, `calculate`
- [x] Grader: score retrieved passages; Rewriter: retry with a better query (max N)
- [x] Synthesizer: answer with page citations
- [x] Groundedness check: every number must appear in the sources; otherwise retry or "insufficient evidence"
- [x] Budget guards: max loops, tokens, timeouts

**Done when:** the agent beats the Phase 2 baseline on the eval set.

### Phase 5: Backend productization (done; caching and Redis dropped)
- [x] SSE streaming of answer and agent steps
- [x] Auth (JWT), chat sessions, history, conversation memory
- [x] Rate limiting, provider fallback
- [x] pytest: unit and API integration tests; CI

### Phase 6: Frontend (done)
- [x] Chat UI with streaming and an agent-steps panel
- [x] Clickable citations showing the source passage and page
- [x] Document list and upload
- [x] Login and history

### Phase 7: Polish (partly done)
- [x] README with eval table and improvement steps
- [ ] Demo GIF / screenshots
- [x] `docs/decisions.md`, limitations section
- [ ] Deploy (optional)

---

## Eval metrics to report

| Metric | Naive RAG | + Hybrid/Rerank | Agentic |
|---|---|---|---|
| Answer accuracy | | | |
| Numeric accuracy | | | |
| Citation correctness | | | |
| Groundedness | | | |
| Multi-hop solved | | | |
| Avg latency / LLM calls | | | |

## Risks

- **PDF tables are messy:** table-aware chunking, check per company, keep page citations so users can verify.
- **Free-tier rate limits:** provider fallback, caching, Ollama for dev.
- **Hallucinated numbers:** calculator tool, groundedness check, "not found" path.
- **Scaling claim:** claim only what is tested, and state how many companies were tested.

---

## Status and next steps
- Done: all phases, real-report validation, search improvements (see README "How it improved").
- Next: full naive/hybrid/agentic table on real reports (needs LLM quota), decode broken-font pages, deploy, Alembic migrations.

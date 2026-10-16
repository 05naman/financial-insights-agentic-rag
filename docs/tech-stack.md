# Tech stack

Agentic RAG over annual-report PDFs. Python backend, React frontend, everything runs locally and free.

## At a glance

| Layer | Main tools |
|---|---|
| Backend | Python 3.12, FastAPI, LangGraph |
| Search | Qdrant, fastembed (bge + BM25), cross-encoder reranker |
| LLM | Groq (free, default), Gemini (free), Ollama (local), with fallback |
| Database | SQLite (default), PostgreSQL (optional) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 |
| Quality | pytest, Vitest, Ruff, oxlint, Husky git hooks |

---

## Backend

### Web API
- **FastAPI**: async REST API with auto docs at `/docs`
- **Uvicorn**: the server
- **Pydantic + pydantic-settings**: request validation and `.env` config
- **Server-Sent Events**: stream the agent's steps to the UI

### Agent
- **LangGraph**: the agent graph (plan, retrieve, grade, calculate, answer, verify)
- **Safe calculator**: AST-based, so the model never does arithmetic itself
- **Grounding check**: plain code that verifies every number against the sources

### LLM providers (`app/llm/`)
- **Groq** (default chain: `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`): free tier, per-model limits
- **Gemini** (`gemini-3.5-flash`): fallback, free tier
- **Ollama**: local, no limits
- Reasoning models: hidden reasoning, `<think>` stripped, empty reply counts as failure
- Usage tally at `/llm/usage`
- **httpx**: direct REST calls (no vendor SDKs)
- Automatic **retry with backoff** on 429 and 5xx, then **fallback** to the next provider

### Document processing
- **pymupdf4llm** (with **pymupdf-layout**): PDF to markdown, tables keep their row labels
- Custom chunker: tables stay whole, with heading and unit line attached
- Running headers and footers removed
- Repairs for real PDFs: spaced numbers, broken bold, rupee sign, split words
- Primary-statement tagging (`retag` command) for ranking boost

### Retrieval
- **Qdrant**: vector database (embedded locally, or a server via Docker)
- **fastembed** (ONNX, CPU only, no PyTorch):
  - `bge-small-en-v1.5`: meaning-based search (dense)
  - `Qdrant/bm25`: keyword search (sparse)
  - `ms-marco-MiniLM`: cross-encoder reranker
- Hybrid search fused with Reciprocal Rank Fusion
- Filters by company and year

### Data and auth
- **SQLAlchemy 2** (async): ORM and repositories
- **SQLite** via aiosqlite: default, zero setup
- **PostgreSQL** via asyncpg: optional, set `DATABASE_URL`
- **PyJWT**: login tokens
- **bcrypt**: password hashing
- In-memory **rate limiter**: per user, with `Retry-After`

### Observability
- Request id on every log line and response (`X-Request-ID`)
- Access log without query strings or bodies
- Redaction filter for tokens, keys, emails, passwords
- Details in [errors-and-logging.md](errors-and-logging.md)

---

## Frontend

### Core
- **React 19** and **TypeScript**
- **Vite 8**: dev server and build
- **React Router 7**: URL per conversation (`/`, `/:id`, `/library`)

### Styling
- **Tailwind CSS 4**: utility classes mapped to CSS variable tokens
- Light and dark themes (system, light, dark), no flash on load
- **Fontsource** (bundled, no external requests):
  - Newsreader: answers and headings
  - IBM Plex Sans: interface
  - IBM Plex Mono: numbers

### Rendering
- **react-markdown** and **remark-gfm**: answers and tables
- Custom footnote markers that open the source passage

### Own building blocks (`src/ui/`)
- `Button`, `IconButton`: every state defined once
- `Alert`, `Toast`: error and status messages
- `ErrorBoundary`, `NetworkBanner`: safety nets
- Fetch-based API layer with typed errors and SSE streaming

---

## Testing and tooling

| Area | Tool | What it covers |
|---|---|---|
| Backend tests | **pytest**, pytest-asyncio, respx | API, agent, ingestion, logging and leak checks |
| Frontend tests | **Vitest**, jsdom | error mapping, citation helpers |
| Browser checks | **Playwright** (run ad hoc) | 24 failure and state scenarios |
| Lint and format | **Ruff**, **oxlint** | Python and TypeScript |
| Mock data | **ReportLab** | generates realistic mock annual reports |
| Eval | custom harness in `backend/evals/` | naive vs hybrid vs agentic |
| Package managers | **uv**, **npm** | Python and JS dependencies |
| Git hooks | **Husky** | lint and type-check before commit, tests and build before push |
| Containers | **Docker**, Docker Compose | optional Postgres and Qdrant |

---

## Free services used
- **Groq API**: free tier (main)
- **Gemini API**: free tier (optional fallback)
- Everything else runs locally


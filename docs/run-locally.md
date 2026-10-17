# Run the project locally

No Docker or Redis needed. Takes about 10 minutes the first time (mostly model downloads).

## What you need
- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node 20+** and npm
- **A free Groq API key** (https://console.groq.com/keys); Gemini key optional (https://aistudio.google.com/apikey)
- Internet on first run (embedding models download once, a few hundred MB)

## Quick start

Run all commands from the project root.

### 1. Backend setup
```bash
cd backend
cp .env.example .env
uv sync
```
Open `backend/.env` and set:
```
GROQ_API_KEY=your_key_here
```
Optional: `GEMINI_API_KEY=...` as a fallback when Groq's free quota runs out.

### 2. Get some reports
Use the mock reports (3 fictional companies × FY2022-24):
```bash
uv run python scripts/make_mock_reports.py
```
This writes 9 PDFs to `data/pdfs/` and the test questions to `backend/evals/questions.json`.

Or use your own PDFs. Name them `TICKER_FYyyyy.pdf`, for example `TCS_FY2024.pdf`, and put them in `data/pdfs/`.

### 3. Ingest the PDFs
```bash
uv run python -m app.cli ingest --dir ../data/pdfs
```
- Reads pages, builds the search index
- Mock reports: about 1 minute. Real reports: about 1 second per page
- Safe to re-run; already-ingested files are skipped

### 4. Start the API
```bash
uv run uvicorn app.main:app --reload
```
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs (only when `ENVIRONMENT=local`; hidden on a deployed server)
- Health check: http://localhost:8000/health

### 5. Start the frontend (new terminal)
```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```
Open http://localhost:5173, click **Create an account**, then ask a question.

## Ports and URLs

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

## Ask from the terminal (no UI)
```bash
cd backend
uv run python -m app.cli ask "What was BHIT revenue in FY2024?" --mode agentic
```
- Modes: `agentic` (full agent), `hybrid`, `naive`
- **Stop the API first.** The local search index allows one process at a time.

## Settings that matter (`backend/.env`)

| Setting | Default | Use |
|---|---|---|
| `GROQ_API_KEY` | empty | Main LLM (free tier) |
| `GEMINI_API_KEY` | empty | Optional fallback |
| `LLM_PROVIDERS` | `groq:qwen/qwen3.8-27b`, `groq:openai/gpt-oss-120b`, `groq:openai/gpt-oss-20b`, `gemini`, `ollama` | Order tried (`provider:model`) |
| `DATABASE_URL` | SQLite file | Postgres: `postgresql+asyncpg://...` |
| `QDRANT_URL` | empty (embedded) | Server: `http://localhost:6333` |
| `JWT_SECRET` | dev value | Change for any shared deployment |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Add your frontend URL if the port changes |

Frontend: `frontend/.env` has `VITE_API_URL=http://localhost:8000`.

## Run the checks
```bash
cd backend
uv run pytest                    # 136 backend tests
uv run ruff check .              # lint
uv run python -m evals.run --retrieval-only    # retrieval quality, no LLM needed

cd ../frontend
npm test                         # 33 unit tests
npm run build                    # type-check + production build
```
Full answer evaluation (needs LLM quota): `uv run python -m evals.run --modes naive hybrid agentic`

## After upgrading an older index
If you ingested reports before the primary-statement tagging existed, tag them once (instant, no re-embedding):
```bash
cd backend && uv run python -m app.cli retag
```

## Git hooks (optional, Husky)
From the project root, run `npm install` once. Then:
- before each **commit**: `ruff` (backend) and `oxlint` + `tsc` (frontend), only for the folders you changed
- before each **push**: backend tests, frontend tests and build
- skip once with `git commit --no-verify`

## Reset everything
```bash
rm -rf backend/data        # database, search index, downloaded models
```
Then ingest again. To keep the model downloads, delete only `backend/data/app.db` and `backend/data/qdrant`.

## Optional: Docker for Postgres and Qdrant
```bash
docker compose up -d
```
Then set `DATABASE_URL` and `QDRANT_URL` in `backend/.env` (examples are in `.env.example`). Not required.

## Troubleshooting

| Problem | Fix |
|---|---|
| "The language model is unavailable" | Key missing or free quota used up. Check `GROQ_API_KEY`, wait, or add `GEMINI_API_KEY` |
| `429` or very slow answers | Free-tier limit. The app retries automatically; try again later |
| Answer says "Insufficient evidence" | The company or year isn't ingested. Check the Library page |
| Library shows a report as **Failed** | PDF is scanned, protected or corrupted. See the backend log |
| Browser shows "Can't reach the server" | API isn't running on port 8000 |
| Login fails with a network error on another port | Add that URL to `CORS_ORIGINS` and restart the API |
| "Storage folder is already accessed" | Stop the API before using the CLI (or the other way round) |
| First start is slow | Models are downloading (once) |
| Upload rejected | File must be a PDF named `TICKER_FYyyyy.pdf`, up to 100 MB |
| Port already in use | Stop the old process, or pass `--port 8001` to uvicorn |

## Where to look when something breaks
- Backend log: the terminal running uvicorn. Every line has a request id.
- Error responses include `request_id`; search the log for it.
- More: [errors-and-logging.md](errors-and-logging.md)

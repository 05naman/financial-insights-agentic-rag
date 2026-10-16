# Financial Insights (Agentic RAG)

An AI research assistant for Indian company annual reports. Upload report PDFs and ask questions like
"How did TCS's revenue and margin change over three years, and what risks does it flag?". An agent plans the
research, searches the right pages, runs calculations, checks that every figure appears in its sources, and
answers with page citations.

- Only your PDFs are used: no data APIs, no scraping. The only outside service is the LLM (free tiers).
- Adding a company means adding its PDFs. No company-specific code.

Docs: [run it](docs/run-locally.md) · [test queries](docs/test-queries.md) · [tech stack](docs/tech-stack.md) · [architecture](docs/architecture.md) · [evaluation](docs/evaluation.md) · [UI design](docs/design.md) · [errors and logging](docs/errors-and-logging.md) · [plan](PLAN.md)

## Results (measured, no LLM needed for the search numbers)

| Test | Plain hybrid search | Improved |
|---|---|---|
| Mock reports, 246 stress queries (found in top 6 / ranking quality) | 89% / 0.74 | **99% / 0.85** |
| Real TCS report (360 pages), 30 questions | 60% / 0.34 | **90% / 0.63** |
| Real Infosys report | 32% | **92%** |
| Real HDFC Bank report | 39% | **61%** |

Real PDFs stay in git-ignored `data/`; only questions and answer keys are in the repo.

## Quick start (no Docker needed)

```bash
# 1. backend
cd backend
cp .env.example .env            # add GROQ_API_KEY (and/or GEMINI_API_KEY)
uv sync

# 2. add reports named TICKER_FYyyyy.pdf, e.g. data/pdfs/TCS_FY2024.pdf, then ingest
uv run python -m app.cli ingest --dir ../data/pdfs

# 3. ask from the terminal, or run the API
uv run python -m app.cli ask "How did TCS revenue change?" --mode agentic
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs

# 4. frontend (new terminal)
cd frontend && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

- First run downloads the embedding models (a few hundred MB) into `backend/data/models`.
- Free keys: [Groq](https://console.groq.com/keys) (default chain), [Gemini](https://aistudio.google.com/apikey).
- No external LLM: install Ollama and set `LLM_PROVIDERS=["ollama"]`.
- Docker (Postgres, Qdrant) is optional.

## Three answer modes

| Mode | What it does | LLM calls |
|---|---|---|
| Naive | dense search only | 1 |
| Hybrid | BM25 + dense + improvements | 1 |
| Agent | plan, filter, search, grade/retry, calculate, answer, verify, memory | 4 to 6 |

## How it improved, step by step (high level)

1. **Phases 0-7 built end to end:** PDF ingestion, hybrid search, LangGraph agent, FastAPI + SSE, React UI, auth, evals.
2. **Eval set first:** 62 mock questions with known answers, scored by plain code (no LLM judge).
3. **Three modes to compare:** naive vs hybrid vs agent, same questions, same data.
4. **Stress test of search:** 246 queries (typos, year formats, exact figures, two companies, held-out wording), no LLM.
5. **Fixes that each earned their place** (leave-one-out ablations):
   - company name added to every passage (biggest win)
   - numbers indexed without commas (`1,89,866` stays one token)
   - typo correction using the reports' own vocabulary
   - auto-detect company and year in the question
   - result: 89% → 99%
6. **Rejected on evidence:** reranker (slow, no gain), synonym list (overfit, no gain on held-out wording), dropping tiny chunks, aggressive header stripping.
7. **Real reports broke the sample-data tuning:** TCS 60%. Notes pages outranked the profit and loss statement.
8. **Primary-statement tagging + boost** on money questions only: TCS 60% → 90%, Infosys 32% → 92%.
9. **Loader repairs for real PDFs:** spaced numbers, broken bold, rupee sign read as "H", split words, ragged tables.
10. **Safer ingestion:** work off the event loop, prepare-then-swap re-upload, page cap, failed-job cleanup at startup.
11. **LLM layer hardened:** Groq-first provider chain, retry/backoff, fail fast on long rate limits, fallback cooldown, token budgets (about 8K tokens per agent question), reasoning-model handling.
12. **Answer safety:** verifier checks every number and citation against sources; refuses instead of guessing.
13. **UI and reliability:** button states, error mapping, SSE parsing, evidence pane that handles unreadable text, rate limits, request-id logs with secret redaction.
14. **Code review fixes:** auth limits, JWT secret check outside local, SQL parameter hiding, empty-session cleanup.
15. **Tests:** 136 backend + 33 frontend, lint and type-check clean.

## Known limits

- Some TCS pages use a broken font (about 10 pages read as `�`); key statements are clean.
- Banks present figures in other units (₹ '000) and wording; HDFC reworded questions are weakest (61%).
- Agent quality on real reports is only lightly tested; free-tier LLM quotas limit big runs.
- Not built: deployment, migrations (Alembic), roles.

## Evaluate

```bash
cd backend
uv run python -m evals.retrieval_stress --limit 5          # search stress test, streams results
uv run python -m evals.real_report --limit 5               # real-report check (needs PDFs)
uv run python -m evals.run --retrieval-only                # no LLM needed
uv run python -m evals.run --modes naive hybrid agentic    # full comparison (uses LLM quota)
```
Method and numbers: [docs/evaluation.md](docs/evaluation.md).

## Tests and checks

```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm test && npm run build
```

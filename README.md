# Financial Insights (Agentic RAG)

Ask questions about Indian company annual reports. An agent plans the research, searches the right pages, runs calculations, checks every figure against its sources, and answers with page citations.

- Uses only the PDFs you supply. No data APIs, no scraping. The LLM (free tier) is the only outside service.
- Adding a company means adding its PDFs, with no company-specific code.

**Stack:** FastAPI, LangGraph, Qdrant, fastembed (dense + BM25), Groq/Gemini/Ollama, SQLite, React + TypeScript + Tailwind.

## Results

Share of questions where the right page is in the top 6, plain hybrid search vs improved:

| Test | Plain | Improved |
|---|---|---|
| Mock reports, 246 stress queries | 85% | **98%** |
| Real TCS report, 30 questions | 33% | **87%** |
| Real Infosys report | 32% | **92%** |
| Real HDFC Bank report | 39% | **61%** |

## Run it

```bash
cd backend && cp .env.example .env && uv sync      # add GROQ_API_KEY to .env
uv run python -m app.cli ingest --dir ../data/pdfs  # PDFs named TICKER_FYyyyy.pdf
uv run uvicorn app.main:app --reload                # http://localhost:8000/docs

cd frontend && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

Free keys: [Groq](https://console.groq.com/keys), [Gemini](https://aistudio.google.com/apikey). Full guide: [docs/run-locally.md](docs/run-locally.md).

## Answer modes

- **Naive:** dense search, 1 LLM call
- **Hybrid:** BM25 + dense with fixes, 1 LLM call
- **Agent:** plan, search, grade/retry, calculate, answer, verify (4 to 6 calls)

## How it improved, step by step

1. Built the full pipeline: ingestion, hybrid search, agent, API, UI, auth.
2. Wrote an eval set with known answers, scored by plain code (no LLM judge).
3. Stress-tested search with 246 queries: typos, year formats, exact figures, held-out wording.
4. Kept only fixes that each proved their worth: company name in every passage, comma-free numbers, typo correction, auto company/year detection (85% → 98%).
5. Dropped what didn't help: reranker, synonym list, tiny-chunk removal.
6. Real reports exposed new problems: notes outranked the financial statements (TCS 33%).
7. Tagged primary statements and boosted them on money questions (TCS 87%, Infosys 92%).
8. Repaired real-PDF text: spaced numbers, broken bold, rupee sign, split words.
9. Hardened the LLM layer: model chain, retries, quota fail-fast, token budgets.
10. Added answer checks (numbers and citations must appear in sources), error handling, and safe logging.

Details and numbers: [docs/evaluation.md](docs/evaluation.md).

## Known limits

- A few pages in some PDFs use broken fonts and read as `�`.
- Bank reports use other units and wording, so reworded questions are weakest (HDFC 61%).
- Not built: deployment, migrations, roles.

## More docs

[Architecture](docs/architecture.md) · [Tech stack](docs/tech-stack.md) · [Test queries](docs/test-queries.md) · [UI design](docs/design.md) · [Errors and logging](docs/errors-and-logging.md) · [Plan](PLAN.md)

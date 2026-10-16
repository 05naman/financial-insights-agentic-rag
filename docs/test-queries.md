# Test queries

Questions to try in the app, with the exact answers. They work on the **mock reports** (for real reports, try e.g. "What was TCS's consolidated revenue from operations in FY2026?" in Agent mode) (see [run-locally.md](run-locally.md)).
Amounts are in ₹ crore, Indian digit grouping (1,89,866 = 189866).
Expected values come straight from the generated data, so they are exact. How the live LLM phrases them can differ.

## The mock companies

| Ticker | Name | Sector | Reports |
|---|---|---|---|
| `BHIT` | Bharat Infotech Limited | IT services | FY2022, FY2023, FY2024 |
| `SAGR` | Sagar Pharma Limited | Pharmaceuticals | FY2022, FY2023, FY2024 |
| `NAVM` | Navbharat Motors Limited | Automobiles | FY2022, FY2023, FY2024 |

## How to test
- **UI:** type the question, check the answer and the footnotes
- **Compare modes:** ask the same question in Agent, Hybrid, Naive (dropdown under the box)
- **Terminal:** `uv run python -m app.cli ask "..." --mode agentic` (stop the API first)
- **Pass means:** the number matches, a footnote cites the right company and year, the badge says **Figures verified**

---

## 1. Single facts (easy)

| Query | Expected |
|---|---|
| What was Bharat Infotech's revenue from operations in FY2024? | 1,89,866 |
| What was Sagar Pharma's revenue from operations in FY2024? | 49,219 |
| What was Navbharat Motors' revenue from operations in FY2024? | 82,875 |
| What was the profit after tax of Bharat Infotech in FY2023? | 32,912 |
| How many employees did Bharat Infotech have as on March 31, 2024? | 3,22,920 |
| How many employees did Navbharat Motors have as on March 31, 2024? | 60,237 |
| What dividend per share did Sagar Pharma recommend for FY2024? | 25.0 |
| What were the total assets of Navbharat Motors as at March 31, 2024? | 43,519 |
| How much cash did Sagar Pharma hold at the end of FY2023? | 4,166 |

## 2. Same facts, different words (robustness)

| Query | Expected |
|---|---|
| What was the turnover of Bharat Infotech in FY2024? | 1,89,866 |
| What was Sagar Pharma's net profit for the year ended March 2023? | 7,065 |
| What was the head count at Navbharat Motors in March 2024? | 60,237 |
| bhit rev fy24 | 1,89,866 (shorthand; a stretch case, may fail) |

## 3. Over several years

| Query | Expected |
|---|---|
| By what percentage did Bharat Infotech's revenue grow from FY2023 to FY2024? | 8.6% |
| By what percentage did Sagar Pharma's revenue grow from FY2023 to FY2024? | 12.1% |
| By what percentage did Navbharat Motors' revenue grow from FY2023 to FY2024? | 7.4% |
| What was Bharat Infotech's revenue in FY2022 and in FY2024? | 1,56,940 and 1,89,866 |
| What was Bharat Infotech's pre-tax margin in FY2022, FY2023 and FY2024? | 25.2%, 24.9%, 24.8% |
| How did Bharat Infotech's revenue change from FY2022 to FY2024, and what are its key risks? | 1,56,940 → 1,89,866 (+32,926, +20.98%), plus 3 risks |

## 4. Calculations (uses the calculator tool)

| Query | Expected |
|---|---|
| CAGR of Bharat Infotech's revenue between FY2022 and FY2024? | 10.0% |
| CAGR of Sagar Pharma's revenue between FY2022 and FY2024? | 14.1% |
| CAGR of Navbharat Motors' revenue between FY2022 and FY2024? | 14.0% |
| Net profit margin (PAT as % of revenue) of Bharat Infotech in FY2024? | 18.6% |
| Net profit margin of Navbharat Motors in FY2024? | 9.8% |
| Debt-to-equity ratio (borrowings ÷ total equity) of Bharat Infotech at March 31, 2024? | 0.07 |
| Debt-to-equity ratio of Navbharat Motors at March 31, 2024? | 0.11 |

In the steps panel ("How this was answered") you should see a **Ran N calculations** step.

## 5. Comparing companies

| Query | Expected |
|---|---|
| Compare the FY2024 profit after tax of Bharat Infotech and Sagar Pharma. | 35,391 vs 8,096 |
| Compare the FY2024 profit after tax of Sagar Pharma and Navbharat Motors. | 8,096 vs 8,130 |
| Which company had the highest revenue growth in FY2024 over FY2023? | Sagar Pharma (12.1%) |
| Which company had the highest pre-tax margin in FY2024? | Bharat Infotech (24.8%) |

## 6. Segments

| Query | Expected |
|---|---|
| Which segment contributed the most revenue to Bharat Infotech in FY2024? | India and Rest of World, 75,911 |
| Which segment contributed the most revenue to Sagar Pharma in FY2024? | Formulations, 21,722 |
| Which segment contributed the most revenue to Navbharat Motors in FY2024? | Spare parts and services, 30,643 |

## 7. Risks (text, not numbers)

| Query | Expected |
|---|---|
| What are the key risks mentioned by Bharat Infotech in its FY2024 report? | Attrition of skilled employees; Currency fluctuation; Client concentration |
| What are the key risks mentioned by Sagar Pharma in its FY2024 report? | Regulatory action by US FDA; Price erosion in generics; Raw material cost volatility |
| What are the key risks mentioned by Navbharat Motors in its FY2024 report? | Semiconductor supply disruption; Transition to electric vehicles; Cyclical demand |
| Which company flags semiconductor supply disruption as a risk? | Navbharat Motors |
| Which company flags regulatory action by US FDA as a risk? | Sagar Pharma |
| Which company flags attrition of skilled employees as a risk? | Bharat Infotech |

## 8. Follow-ups (ask two questions in the same chat)

| First | Then | Expected |
|---|---|---|
| What was Bharat Infotech's revenue from operations in FY2024? | And what was it in FY2023? | 1,74,831 |
| What was Sagar Pharma's profit after tax in FY2024? | How about their employee count? | 42,953 |
| What was Bharat Infotech's profit after tax in FY2024? | Now do the same for Navbharat Motors. | 8,130 |

Agent mode should handle these. Naive and Hybrid usually can't (they have no memory), which is expected.

## 9. Must refuse ("Insufficient evidence" or an out-of-scope message)

| Query | Why |
|---|---|
| What will Bharat Infotech's revenue be in FY2026? | Future, not in reports |
| What is the current share price of Sagar Pharma? | Not in annual reports |
| What was Infosys's revenue in FY2024? | Company not loaded |
| What was Bharat Infotech's revenue in FY2025? | Year not loaded |
| What was the salary of the Managing Director of Sagar Pharma in FY2024? | Not disclosed in the mock reports |
| Should I buy Navbharat Motors shares? | Investment advice, refused |
| Tell me a joke | Out of scope (depends on the model recognising it) |

**A wrong number here is a bug**, since the system should never guess.

---

## App behaviour checks

| Try | Should happen |
|---|---|
| Click a footnote number | Evidence pane opens with the source page; matching figures highlighted |
| Press the **Stop** button during an answer | Shows "Stopped before the answer finished" |
| Ctrl/Cmd + K | New question, cursor in the box |
| Reload on a saved chat URL | Conversation comes back |
| Switch the theme (sun / monitor / moon) | Both themes work; choice is remembered |
| Library: upload `report.pdf` | Rejected: rename to `TICKER_FYyyyy.pdf` |
| Library: upload `notes.txt` | Rejected: not a PDF |
| Library: upload a valid PDF named `TCS_FY2024.pdf` | Status goes Queued → Reading pages → Ready |
| Stop the API, then ask something | "Can't reach the server", with **Try again** |
| Remove the LLM keys (Groq, Gemini), then ask | "language model unavailable" message, no key names shown |
| Ask 21 questions within a minute | Rate-limit message with a wait time |

## API smoke test (curl)
```bash
curl localhost:8000/health

curl -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"password123"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"password123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl localhost:8000/documents -H "Authorization: Bearer $TOKEN"
```

## Run the same set automatically
```bash
cd backend
uv run python -m evals.run --retrieval-only                    # no LLM
uv run python -m evals.run --modes naive hybrid agentic        # needs LLM quota
uv run python -m evals.run --modes agentic --category calculation --limit 5
```
Categories: `single_fact`, `paraphrase`, `multi_year`, `segments`, `risks`, `multi_company`, `calculation`, `follow_up`, `unanswerable`.
Method and scoring: [evaluation.md](evaluation.md).

## Test the search only (no LLM, no quota)
Shows exactly which passages the index returns, with scores. Stop the API first (the local index allows one process).
```bash
cd backend
uv run python -m app.cli search "revenue from operations" --company BHIT --year 2024
uv run python -m app.cli search "how much money did the company earn after paying taxes" --company SAGR --year 2024 --mode dense
```
Options: `--mode dense | hybrid | rerank`, `--company` and `--year` (repeatable), `--limit`, `--width`.

| Check | Try | Good result |
|---|---|---|
| Meaning, not just words | `"how much money did the company earn after paying taxes"` (SAGR, 2024) | Profit and Loss table (page 5) or Highlights (page 3) ranks first |
| Right company and year | any query with `--company BHIT --year 2024` | every hit says `BHIT FY2024` |
| Tables are searchable | `"debt to equity borrowings total equity"` | balance sheet table (page 6) |
| Risks section | `"what could hurt margins"` (BHIT, 2024) | page 4, "Risks and Concerns" |
| Compare modes | same query with `--mode dense`, `hybrid`, `rerank` | similar top hits; `rerank` is slowest |
| Whole-set score | `uv run python -m evals.run --retrieval-only` | recall per category, no LLM needed |

Exact figures now work too: `"1,89,866"` finds the pages that contain it (numbers are indexed without commas).
Typos are fixed against the reports' own words (`employes` finds employees).

Harder, wider test (246 queries, results stream live): see "Retrieval stress test" in [evaluation.md](evaluation.md).
```bash
uv run python -m evals.retrieval_stress --limit 5       # 5 mixed tests, each printed as it finishes
```
After changing an indexing option in `config.py`, rebuild with `uv run python -m app.cli ingest --replace`.

## If you regenerate the mock data
The numbers come from a fixed seed, so they stay the same. If you change `scripts/make_mock_reports.py`, check them in
`backend/evals/mock_truth.json`.

# Error handling and logging

## Principles
1. **Users see a clear, actionable message. Operators see the cause in the logs.** The two are linked by a request id.
2. **Nothing sensitive reaches a log or a response:** no passwords, tokens, API keys, emails, SQL parameters, file
   paths, question text, or provider error bodies.
3. **Every failure has a way forward:** retry, edit, or a plain explanation.

## Backend
| Situation | Response | Logged |
|---|---|---|
| Unexpected crash | `500` JSON `{detail, request_id}`, generic text | full traceback with request id |
| Language model down or rate-limited | `502` generic message (stream: `error` event) | provider names and status, no secrets |
| Too many requests | `429` + `Retry-After` | access-log line |
| Bad upload (not a PDF, empty, too large, bad name, already processing) | `422` / `413` / `409` with a specific reason | one line, no file contents |
| Ingestion failure on a PDF | document marked `failed` with a generic message | full exception and traceback |
| Auth | `401` generic "Invalid email or password" | `login failed` without the email |

- Every response carries `X-Request-ID` (accepts one from the client). It is in every log line and in 500 responses, so a
  user report of "reference ab12cd34" finds the exact trace.
- One access-log line per request: method, path, status, duration. No query strings, headers or bodies.
- Business events log ids and counts only (`user=3 session=12 mode=agentic q_len=48 llm_calls=4`), never text.
- `SafeFormatter` redacts bearer tokens, JWTs, API-key shapes, `password=` style pairs, configured secrets and email
  addresses from every line, including tracebacks. SQLAlchemy runs with `hide_parameters=True`.
- Noisy libraries (`httpx`, `qdrant_client`) are quieted to warnings; uvicorn's own access log is off (ours replaces it).
- Abandoned empty chat sessions are hidden and purged.

## Frontend
- One API layer (`src/api/client.ts`) maps every failure to an `ApiError` with a kind and a human message:
  network, timeout, offline, 401 (session expired), 403, 404, 409, 413, 422 (field messages), 429 (with wait time),
  5xx (with reference id), unreadable body. Streams also handle idle timeouts, dropped connections and streams that end
  without an answer.
- A 401 anywhere ends the session and shows the login page with an explanation. A server outage at startup does **not**
  log the user out.
- Surfaces: inline `Alert` with retry for page-level failures, toasts for transient ones (delete failed, copy failed,
  upload result), an offline banner, a 404 page, and an error boundary so a render crash never blanks the app.
- All buttons come from `Button` / `IconButton`, which define rest, hover, pressed, keyboard focus, disabled and loading
  states once. Loading buttons are disabled and `aria-busy`, which also prevents double submits.

## How it is tested
- Backend: leak tests (no email/password/question/provider detail in logs or responses), redaction unit tests, request-id
  tests, upload validation, 502/500 behaviour.
- Frontend: unit tests for error mapping and citation helpers, and 24 browser scenarios (network down, 401, 429, 500,
  truncated stream, bad uploads, offline, focus rings, hover, loading states).

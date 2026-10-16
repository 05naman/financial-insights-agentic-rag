import logging
import re
from contextvars import ContextVar

# Correlates every log line of one request; also returned to the client as X-Request-ID.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Patterns for secrets that must never reach a log file, even by accident (URLs, headers, tracebacks).
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I), "Bearer [REDACTED]"),
    (re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), "[REDACTED_JWT]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_KEY]"),  # Google API keys
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "[REDACTED_KEY]"),  # Groq API keys
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "[REDACTED_KEY]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|x-goog-api-key|authorization|password|passwd|secret|token)\b(\s*[=:]\s*)\S+"
        ),
        r"\1\2[REDACTED]",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),  # personal data: no emails in logs
]
_extra_secrets: list[str] = []


def register_secrets(*values: str) -> None:
    """Exact values (API keys, signing secret) to scrub wherever they appear."""
    for v in values:
        if v and len(v) >= 6 and v not in _extra_secrets:
            _extra_secrets.append(v)


def redact(text: str) -> str:
    for secret in _extra_secrets:
        text = text.replace(secret, "[REDACTED]")
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class SafeFormatter(logging.Formatter):
    """Adds the request id and redacts secrets from the final line, including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return redact(super().format(record))


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        SafeFormatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # our request middleware writes the access log (without query strings), so uvicorn's duplicate is off
    logging.getLogger("uvicorn.access").disabled = True
    # these log full outbound URLs/headers at INFO: keep them to warnings
    for noisy in ("httpx", "httpcore", "urllib3", "qdrant_client", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

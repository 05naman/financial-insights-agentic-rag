from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-change-me-in-production-0000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Financial Insights"
    environment: str = "local"
    log_level: str = "INFO"

    # SQLite by default so the app runs without Docker; use Postgres via DATABASE_URL
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # Qdrant: server URL if set, otherwise embedded local storage at qdrant_path
    qdrant_url: str = ""
    qdrant_path: str = "./data/qdrant"
    qdrant_collection: str = "annual_reports"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 60 * 24
    rate_limit_per_minute: int = 20
    auth_rate_limit_per_minute: int = 10
    max_pdf_pages: int = 800
    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_mb: int = 100

    pdf_dir: str = "../data/pdfs"
    # optional {"TCS": "Tata Consultancy Services Limited"} so questions can use company names
    companies_file: str = "../data/companies.json"

    dense_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    embedding_cache_dir: str = "./data/models"

    # Retrieval-quality options, each measured with `python -m evals.retrieval_stress --ablate`.
    # Changing an `index_*` option needs `python -m app.cli ingest --replace` to take effect.
    index_normalize_numbers: bool = (
        True  # keyword index sees "1,89,866" as one token (+exact figures)
    )
    index_company_name: bool = (
        True  # passages carry the company name in their search header (+ranking)
    )
    index_drop_tiny_chunks: bool = (
        False  # page labels and lone headings; see evaluation.md for the real-report result
    )
    index_boilerplate_share: float = (
        0.4  # a line repeated on this share of pages is a running header/footer
    )
    query_spell_correct: bool = True  # fix typos against the reports' own vocabulary
    query_synonyms: bool = (
        False  # measured: no gain on unseen wording (it only helped phrasings it was written for)
    )
    # extra rank score for primary-statement tables on money questions (0 = off). 0.6 measured: real TCS
    # report 60% -> 90% found, sample set unchanged. Run `python -m app.cli retag` once on older indexes.
    query_statement_boost: float = 0.6
    # False: apply the boost to every question (compared against the risk questions in the stress test)
    query_boost_financial_only: bool = True
    query_auto_filters: bool = True  # find company/year in the question when none were given

    # how much evidence each LLM call carries. Free tiers cap tokens per minute and per day, so keep it lean.
    agent_top_k: int = 5
    agent_max_evidence: int = 8
    agent_passage_chars: int = 1200

    chunk_size: int = 1000
    chunk_overlap: int = 150

    # LLM providers, tried in this order. Supported: gemini, groq, ollama
    llm_providers: list[str] = [
        "groq:qwen/qwen3.8-27b",
        "groq:openai/gpt-oss-120b",
        "groq:openai/gpt-oss-20b",
        "gemini",
        "ollama",
    ]
    llm_timeout_seconds: float = 60.0

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # minimal | low | medium | high. Higher = slower, and "thinking" tokens eat the output budget
    gemini_thinking_level: str = "minimal"

    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"


@lru_cache
def get_settings() -> Settings:
    return Settings()

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, documents, health, llm
from app.core.config import DEFAULT_JWT_SECRET, get_settings
from app.core.logging import register_secrets, request_id_var, setup_logging
from app.db.repositories import DocumentRepository
from app.db.session import get_sessionmaker, init_db
from app.llm.base import LLMError

logger = logging.getLogger(__name__)
settings = get_settings()
register_secrets(settings.gemini_api_key, settings.groq_api_key, settings.jwt_secret)
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment != "local" and settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET must be changed from the default when ENVIRONMENT is not 'local'"
        )
    await init_db()
    async with (
        get_sessionmaker()() as session
    ):  # anything left mid-ingestion by a crash can never finish
        n = await DocumentRepository(session).fail_stale_processing()
        if n:
            logger.warning("marked %d interrupted ingestion(s) as failed", n)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id + one access-log line per request + clean JSON for unexpected crashes.

    Logs method, path, status and timing only: never bodies, query strings or headers (they can hold
    passwords, tokens and questions). Registered before CORS so error responses keep CORS headers."""
    request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse(
                {
                    "detail": "Something went wrong on our side. Please try again.",
                    "request_id": request_id,
                },
                status_code=500,
            )
        response.headers["X-Request-ID"] = request_id
        if request.url.path != "/health":
            ms = (time.perf_counter() - started) * 1000
            level = (
                logging.ERROR
                if response.status_code >= 500
                else logging.WARNING
                if response.status_code >= 400
                else logging.INFO
            )
            logger.log(
                level,
                "%s %s -> %s in %.0fms",
                request.method,
                request.url.path,
                response.status_code,
                ms,
            )
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    logger.warning(
        "language model unavailable: %s", exc
    )  # detail stays in the log, not the response
    return JSONResponse(
        {"detail": "The language model is unavailable or rate-limited. Please try again shortly."},
        status_code=502,
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
for router in (health.router, auth.router, documents.router, chat.router, llm.router):
    app.include_router(router)

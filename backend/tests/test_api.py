import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.deps import reset_limiter
from app.container import Container, get_container
from app.core.config import get_settings
from app.db.session import reset_engine
from app.main import app
from app.retrieval.vector_store import VectorStore
from tests.conftest import FakeEmbedder, make_pdf
from tests.test_agent import ScriptedLLM

CREDS = {"email": "a@example.com", "password": "password123"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("PDF_DIR", str(tmp_path / "pdfs"))
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    get_settings.cache_clear()
    reset_engine()
    reset_limiter()

    llm = ScriptedLLM()
    container = Container.__new__(Container)
    container.settings = get_settings()
    container.embedder = FakeEmbedder()
    container.reranker = None
    container.store = VectorStore(QdrantClient(":memory:"), "t", container.embedder.dim)
    from app.retrieval.retriever import Retriever

    container.retriever = Retriever(container.embedder, container.store, None)
    container.llm = llm
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as c:
        c.llm = llm
        yield c
    app.dependency_overrides.clear()
    reset_engine()
    get_settings.cache_clear()
    reset_limiter()


def auth(client) -> dict:
    client.post("/auth/register", json=CREDS)
    token = client.post("/auth/login", json=CREDS).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, tmp_path, name="TCS_FY2024.pdf"):
    p = tmp_path / name
    make_pdf(p, ["Revenue from operations was Rs 2,40,893 crore in FY2024."])
    with p.open("rb") as f:
        return client.post(
            "/documents", files={"file": (name, f, "application/pdf")}, headers=headers
        )


def test_auth_flow(client):
    assert client.post("/auth/register", json=CREDS).status_code == 201
    assert client.post("/auth/register", json=CREDS).status_code == 409
    assert client.post("/auth/login", json={**CREDS, "password": "wrongpass1"}).status_code == 401
    h = auth(client)
    assert client.get("/auth/me", headers=h).json()["email"] == CREDS["email"]
    assert client.get("/auth/me").status_code == 401
    assert client.get("/documents").status_code == 401


def test_upload_rejects_bad_filename(client, tmp_path):
    h = auth(client)
    assert upload(client, h, tmp_path, "report.pdf").status_code == 422


def test_upload_then_ask(client, tmp_path):
    h = auth(client)
    assert upload(client, h, tmp_path).status_code == 202
    docs = client.get("/documents", headers=h).json()  # background task already ran in TestClient
    assert docs[0]["status"] == "ready" and docs[0]["ticker"] == "TCS"

    sid = client.post("/chat/sessions", headers=h).json()["id"]
    r = client.post(
        f"/chat/sessions/{sid}/ask", json={"question": "TCS revenue FY2024?"}, headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert "2,40,893" in body["answer"] and body["citations"][0]["ticker"] == "TCS"

    msgs = client.get(f"/chat/sessions/{sid}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.get("/chat/sessions", headers=h).json()[0]["title"].startswith("TCS revenue")


def test_sessions_are_private(client, tmp_path):
    h1 = auth(client)
    sid = client.post("/chat/sessions", headers=h1).json()["id"]
    other = {"email": "b@example.com", "password": "password123"}
    client.post("/auth/register", json=other)
    t = client.post("/auth/login", json=other).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t}"}
    assert client.get(f"/chat/sessions/{sid}/messages", headers=h2).status_code == 404


def test_stream_emits_steps_then_final(client, tmp_path):
    h = auth(client)
    upload(client, h, tmp_path)
    sid = client.post("/chat/sessions", headers=h).json()["id"]
    r = client.post(
        f"/chat/sessions/{sid}/stream", json={"question": "TCS revenue FY2024?"}, headers=h
    )
    assert r.status_code == 200
    events = [line.split(": ", 1)[1] for line in r.text.splitlines() if line.startswith("event:")]
    assert events[0] == "step" and events[-1] == "final" and "error" not in events
    assert len(client.get(f"/chat/sessions/{sid}/messages", headers=h).json()) == 2


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    reset_limiter()
    h = auth(client)
    sid = client.post("/chat/sessions", headers=h).json()["id"]
    codes = [
        client.post(
            f"/chat/sessions/{sid}/ask", json={"question": "hello there"}, headers=h
        ).status_code
        for _ in range(3)
    ]
    assert codes[-1] == 429
    blocked = client.post(f"/chat/sessions/{sid}/ask", json={"question": "hello there"}, headers=h)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_delete_document_removes_vectors(client, tmp_path):
    h = auth(client)
    upload(client, h, tmp_path)
    doc_id = client.get("/documents", headers=h).json()[0]["id"]
    assert client.delete(f"/documents/{doc_id}", headers=h).status_code == 204
    assert client.get("/documents", headers=h).json() == []


def test_upload_rejects_non_pdf_empty_and_oversize(client, tmp_path, monkeypatch):
    h = auth(client)

    def post(content: bytes, name="TCS_FY2024.pdf"):
        return client.post(
            "/documents", files={"file": (name, content, "application/pdf")}, headers=h
        )

    r = post(b"this is not a pdf")
    assert r.status_code == 422 and "not a PDF" in r.json()["detail"]
    assert post(b"").status_code == 422
    assert not list((tmp_path / "pdfs").rglob("*.part"))  # no temp files left behind

    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    get_settings.cache_clear()
    container = client.app.dependency_overrides[get_container]()
    container.settings = get_settings()  # the test container reads the new limit
    r = post(b"%PDF-1.4 " + b"x" * 2048)
    assert r.status_code == 413
    assert not [f for f in (tmp_path / "pdfs").rglob("*") if f.is_file()]  # nothing kept


def test_upload_conflict_while_processing(client, tmp_path):
    import asyncio

    from app.db.models import DocumentStatus
    from app.db.repositories import DocumentRepository
    from app.db.session import get_sessionmaker

    h = auth(client)

    async def make_processing():
        async with get_sessionmaker()() as s:
            repo = DocumentRepository(s)
            doc = await repo.create("TCS", 2024, "TCS_FY2024.pdf")
            await repo.set_status(doc, DocumentStatus.processing)

    asyncio.run(make_processing())
    r = upload(client, h, tmp_path)
    assert r.status_code == 409 and "still being processed" in r.json()["detail"]


def test_llm_failure_is_502_with_clean_message(client, tmp_path):
    from app.llm.base import LLMError

    class Down:
        async def generate(self, *a, **k):
            raise LLMError("quota")

    h = auth(client)
    upload(client, h, tmp_path)
    app.dependency_overrides[get_container]().llm = Down()
    sid = client.post("/chat/sessions", headers=h).json()["id"]
    r = client.post(
        f"/chat/sessions/{sid}/ask", json={"question": "TCS revenue?", "mode": "naive"}, headers=h
    )
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]
    assert "quota" not in r.text  # provider details are not leaked


def test_unexpected_error_returns_json_with_request_id(client):
    from fastapi import APIRouter

    boom = APIRouter()

    @boom.get("/__boom")
    async def _boom():
        raise RuntimeError("secret internals")

    client.app.include_router(boom)
    r = TestClient(client.app, raise_server_exceptions=False).get("/__boom")
    assert r.status_code == 500
    body = r.json()
    assert body["request_id"] and "secret" not in r.text
    assert r.headers["x-request-id"] == body["request_id"]


def test_abandoned_empty_sessions_are_not_listed(client):
    h = auth(client)
    client.post("/chat/sessions", headers=h)  # created, never asked anything
    assert client.get("/chat/sessions", headers=h).json() == []


def test_old_empty_sessions_are_purged_but_recent_and_used_ones_stay(client):
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.models import ChatSession
    from app.db.session import get_sessionmaker

    h = auth(client)
    old_empty = client.post("/chat/sessions", headers=h).json()["id"]
    client.post(
        "/chat/sessions", headers=h
    )  # recent and empty: kept for now (a request may be in flight)

    async def age(session_id):
        async with get_sessionmaker()() as s:
            await s.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(created_at=datetime.now(UTC) - timedelta(hours=1))
            )
            await s.commit()

    asyncio.run(age(old_empty))
    client.get("/chat/sessions", headers=h)  # triggers the purge

    async def ids():
        from sqlalchemy import select

        async with get_sessionmaker()() as s:
            return [i for (i,) in await s.execute(select(ChatSession.id))]

    remaining = asyncio.run(ids())
    assert old_empty not in remaining and len(remaining) == 1


def test_health_deps_reports_database_and_index_for_a_logged_in_user(client):
    h = auth(client)
    r = client.get("/health/deps", headers=h)
    assert r.status_code == 200
    assert r.json() == {"database": "ok", "search_index_passages": 0, "search_index": "ok"}

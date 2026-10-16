import logging

import pytest

from app.core.logging import SafeFormatter, redact, register_secrets, request_id_var
from tests.test_api import CREDS, auth, client, upload  # noqa: F401  (fixtures/helpers)


def test_redacts_common_secret_shapes():
    register_secrets("my-super-secret-signing-key")
    samples = {
        "Authorization: Bearer abc.def.ghi-123": "abc.def.ghi-123",
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijk": "eyJhbGciOiJIUzI1NiJ9",
        "key=AIzaSyA1234567890abcdefghijklmnopqrstu": "AIzaSyA1234567890",
        "using gsk_abcdefghijklmnopqrstuvwxyz1234": "gsk_abcdefghijkl",
        "password=hunter2 and api_key: s3cr3t": "hunter2",
        "jwt secret is my-super-secret-signing-key": "my-super-secret-signing-key",
        "user jane.doe@example.com failed": "jane.doe@example.com",
    }
    for text, leaked in samples.items():
        out = redact(text)
        assert leaked not in out, (text, out)
    assert "[REDACTED" in redact("Authorization: Bearer abc.def.ghi-123")


def test_formatter_redacts_tracebacks_and_adds_request_id():
    fmt = SafeFormatter("[%(request_id)s] %(message)s")
    token = request_id_var.set("req123")
    try:
        try:
            raise RuntimeError("failed for password=hunter2")
        except RuntimeError:
            import sys

            record = logging.LogRecord("t", logging.ERROR, "f", 1, "boom", None, sys.exc_info())
        line = fmt.format(record)
    finally:
        request_id_var.reset(token)
    assert "[req123]" in line and "hunter2" not in line


def test_access_log_has_request_id_and_no_secrets(client, caplog):  # noqa: F811
    caplog.set_level(logging.INFO, logger="app.main")
    h = auth(client)
    r = client.get("/auth/me?token=should-not-be-logged", headers={**h, "X-Request-ID": "trace-42"})
    assert r.headers["x-request-id"] == "trace-42"
    text = "\n".join(rec.getMessage() for rec in caplog.records if rec.name.startswith("app"))
    assert "GET /auth/me -> 200" in text
    assert "should-not-be-logged" not in text  # query strings are never logged
    assert h["Authorization"].split()[-1] not in text  # nor tokens


def test_auth_logs_never_contain_email_or_password(client, caplog):  # noqa: F811
    caplog.set_level(logging.INFO)
    client.post("/auth/register", json=CREDS)
    client.post("/auth/login", json={**CREDS, "password": "wrong-password-1"})
    client.post("/auth/login", json=CREDS)
    text = "\n".join(rec.getMessage() for rec in caplog.records if rec.name.startswith("app"))
    assert "user registered" in text and "login failed" in text and "login ok" in text
    assert CREDS["email"] not in text
    assert CREDS["password"] not in text and "wrong-password-1" not in text


def test_question_text_is_not_logged(client, tmp_path, caplog):  # noqa: F811
    caplog.set_level(logging.INFO)
    h = auth(client)
    upload(client, h, tmp_path)
    sid = client.post("/chat/sessions", headers=h).json()["id"]
    client.post(
        f"/chat/sessions/{sid}/ask", json={"question": "my confidential question text"}, headers=h
    )
    text = "\n".join(rec.getMessage() for rec in caplog.records if rec.name.startswith("app"))
    assert "answered user=" in text and "q_len=" in text
    assert "confidential" not in text


def test_llm_outage_does_not_leak_provider_details(client, tmp_path):  # noqa: F811
    from app.agent.nodes import INSUFFICIENT  # noqa: F401
    from app.container import get_container
    from app.llm.base import LLMError
    from app.main import app

    class Down:
        async def generate(self, *a, **k):
            raise LLMError(
                "all providers failed: GEMINI_API_KEY is not set | http://internal:1234 refused"
            )

    h = auth(client)
    upload(client, h, tmp_path)
    app.dependency_overrides[get_container]().llm = Down()
    sid = client.post("/chat/sessions", headers=h).json()["id"]
    body = client.post(
        f"/chat/sessions/{sid}/ask", json={"question": "TCS revenue?"}, headers=h
    ).text
    assert "GEMINI_API_KEY" not in body and "internal" not in body and "unavailable" in body
    assert "GEMINI_API_KEY" not in client.post("/llm/test", json={}, headers=h).text


def test_failed_ingestion_message_is_generic(client, tmp_path):  # noqa: F811
    from app.ingestion.pipeline import SAFE_INGEST_ERROR

    h = auth(client)
    bad = tmp_path / "BAD_FY2024.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated garbage")
    with bad.open("rb") as f:
        client.post("/documents", files={"file": (bad.name, f, "application/pdf")}, headers=h)
    doc = client.get("/documents", headers=h).json()[0]
    assert doc["status"] == "failed" and doc["error"] == SAFE_INGEST_ERROR
    assert str(tmp_path) not in doc["error"]


@pytest.mark.parametrize("path", ["/documents", "/chat/sessions"])
def test_unauthenticated_errors_are_json_without_internals(client, path):  # noqa: F811
    r = client.get(path)
    assert r.status_code == 401 and set(r.json()) == {"detail"}

"""Every API route needs a login, except a short, explicit list of public ones."""

from fastapi.testclient import TestClient

from app.main import app

PUBLIC = {
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
}


def _routes():
    """Every (method, path) the API exposes, read from its OpenAPI schema."""
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/__"):  # routes other tests add to the shared app
            continue
        for method in operations:
            yield method.upper(), path


def test_every_non_public_route_rejects_requests_without_a_token():
    client = TestClient(app)
    checked = 0
    for method, path in _routes():
        if (method, path) in PUBLIC:
            continue
        url = path.replace("{session_id}", "1").replace("{document_id}", "1")
        r = client.request(method, url)
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a token"
        checked += 1
    assert checked >= 10


def test_a_bad_token_is_rejected_too():
    client = TestClient(app)
    r = client.get("/chat/sessions", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_the_public_list_matches_reality():
    paths = set(_routes())
    assert PUBLIC <= paths  # no stale entry hiding a removed route


def test_health_deps_needs_a_login():
    assert TestClient(app).get("/health/deps").status_code == 401


def test_api_docs_are_hidden_outside_local():
    from fastapi import FastAPI

    from app.main import docs_urls

    prod = TestClient(FastAPI(**docs_urls("production")))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod.get(path).status_code == 404, path
    dev = TestClient(FastAPI(**docs_urls("local")))
    assert dev.get("/docs").status_code == 200

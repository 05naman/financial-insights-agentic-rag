"""Access token + refresh token: short access tokens, rotating single-use refresh cookies."""
# ruff: noqa: F811  (the imported `client` fixture is re-declared as each test's argument)

from datetime import timedelta

from app.api import auth as auth_routes
from app.core.config import get_settings
from tests.test_api import CREDS, client  # noqa: F401  (the shared API fixture)

XHR = {"X-Requested-With": "fetch"}


def sign_in(client):
    client.post("/auth/register", json=CREDS)
    r = client.post("/auth/login", json=CREDS)
    assert r.status_code == 200
    return r


def test_login_gives_a_short_access_token_and_an_httponly_refresh_cookie(client):
    r = sign_in(client)
    assert r.json()["access_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie and "httponly" in cookie and "path=/auth" in cookie
    assert "samesite=lax" in cookie
    assert get_settings().jwt_expire_minutes == 15


def test_refresh_needs_the_header_and_the_cookie(client):
    assert client.post("/auth/refresh").status_code == 403  # no header
    assert client.post("/auth/refresh", headers=XHR).status_code == 401  # no cookie
    sign_in(client)
    assert client.post("/auth/refresh").status_code == 403  # cookie but no header


def test_refresh_rotates_the_cookie_and_gives_a_working_access_token(client):
    first = sign_in(client).cookies["refresh_token"]
    r = client.post("/auth/refresh", headers=XHR)
    assert r.status_code == 200
    second = r.cookies["refresh_token"]
    assert second != first
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == CREDS["email"]


def test_a_reused_old_token_revokes_the_whole_family(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "REUSE_LEEWAY", timedelta(0))
    old = sign_in(client).cookies["refresh_token"]
    new = client.post("/auth/refresh", headers=XHR).cookies["refresh_token"]
    # the thief replays the old (already used) token
    client.cookies.clear()
    client.cookies.set("refresh_token", old, path="/auth")
    assert client.post("/auth/refresh", headers=XHR).status_code == 401
    # ...and the legitimate newest token is dead too: sign in again
    client.cookies.clear()
    client.cookies.set("refresh_token", new, path="/auth")
    assert client.post("/auth/refresh", headers=XHR).status_code == 401


def test_two_tabs_refreshing_at_once_is_not_treated_as_theft(client):
    old = sign_in(client).cookies["refresh_token"]
    assert client.post("/auth/refresh", headers=XHR).status_code == 200
    client.cookies.clear()
    client.cookies.set("refresh_token", old, path="/auth")  # the second tab still holds the old one
    assert client.post("/auth/refresh", headers=XHR).status_code == 200


def test_logout_makes_the_refresh_token_useless(client):
    sign_in(client)
    assert client.post("/auth/logout").status_code == 403  # needs the header too
    assert client.post("/auth/logout", headers=XHR).status_code == 204
    client.cookies.set("refresh_token", "anything", path="/auth")
    assert client.post("/auth/refresh", headers=XHR).status_code == 401


def test_logout_revokes_even_inside_the_reuse_window(client):
    token = sign_in(client).cookies["refresh_token"]
    client.post("/auth/refresh", headers=XHR)  # token is now "just used"
    client.post("/auth/logout", headers=XHR)
    client.cookies.set("refresh_token", token, path="/auth")
    assert client.post("/auth/refresh", headers=XHR).status_code == 401


def test_an_expired_refresh_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("REFRESH_TOKEN_DAYS", "0")
    get_settings.cache_clear()
    sign_in(client)
    assert client.post("/auth/refresh", headers=XHR).status_code == 401


def test_an_expired_access_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "-1")
    get_settings.cache_clear()
    token = sign_in(client).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_only_a_hash_of_the_refresh_token_is_stored(client):
    import asyncio

    from sqlalchemy import select

    from app.db.models import RefreshToken
    from app.db.session import get_sessionmaker

    raw = sign_in(client).cookies["refresh_token"]

    async def rows():
        async with get_sessionmaker()() as s:
            return [r.token_hash for r in await s.scalars(select(RefreshToken))]

    stored = asyncio.run(rows())
    assert stored and raw not in stored and all(len(h) == 64 for h in stored)

from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from tests.conftest import register


async def test_register_login_me_logout(client: AsyncClient) -> None:
    user = await register(client, "Alice@Example.com")
    assert user["email"] == "alice@example.com"
    assert get_settings().COOKIE_NAME in client.cookies
    assert (await client.get("/api/auth/me")).json()["email"] == "alice@example.com"

    r = await client.post("/api/auth/logout")
    assert r.status_code == 204
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401

    r = await client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Passw0rd!"})
    assert r.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_cookie_flags(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "c@example.com", "password": "Passw0rd1"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "max-age=" in cookie


async def test_wrong_password_and_unknown_user_are_generic_401(client: AsyncClient) -> None:
    await register(client, "bob@example.com")
    client.cookies.clear()
    r1 = await client.post("/api/auth/login", json={"email": "bob@example.com", "password": "Wrong1234"})
    r2 = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong1234"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"] == "Invalid email or password"


async def test_duplicate_email_409(client: AsyncClient) -> None:
    await register(client, "dup@example.com")
    r = await client.post("/api/auth/register", json={"email": "DUP@example.com", "password": "Passw0rd!"})
    assert r.status_code == 409


async def test_weak_password_422(client: AsyncClient) -> None:
    for pw in ("short1", "allletters", "12345678"):
        r = await client.post("/api/auth/register", json={"email": "w@example.com", "password": pw})
        assert r.status_code == 422, pw


async def test_invalid_email_422(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "not-an-email", "password": "Passw0rd!"})
    assert r.status_code == 422


async def test_protected_endpoints_require_cookie(client: AsyncClient) -> None:
    for method, path in [
        ("GET", "/api/auth/me"),
        ("GET", "/api/documents"),
        ("POST", "/api/documents/upload-url"),
        ("GET", "/api/chat/conversations"),
        ("POST", "/api/chat/conversations"),
    ]:
        r = await client.request(method, path)
        assert r.status_code == 401, path
    assert (await client.get("/api/health")).status_code == 200


async def test_tampered_token_401(client: AsyncClient) -> None:
    client.cookies.set(get_settings().COOKIE_NAME, "not.a.jwt")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_registration_disabled_403(client: AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.routers import auth

    monkeypatch.setattr(auth.settings, "ALLOW_REGISTRATION", False)
    r = await client.post("/api/auth/register", json={"email": "x@example.com", "password": "Passw0rd!"})
    assert r.status_code == 403


async def test_users_cannot_read_each_others_conversations(client: AsyncClient) -> None:
    await register(client, "owner@example.com")
    conv = (await client.post("/api/chat/conversations")).json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, "intruder@example.com")
        assert (await other.get(f"/api/chat/conversations/{conv['id']}")).status_code == 404
        assert (await other.delete(f"/api/chat/conversations/{conv['id']}")).status_code == 404
        r = await other.post(f"/api/chat/conversations/{conv['id']}/messages?stream=false", json={"content": "hi"})
        assert r.status_code == 404
        assert (await other.get("/api/chat/conversations")).json()["total"] == 0

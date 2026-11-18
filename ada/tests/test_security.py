"""Hardening checks: rate limiting, streaming body cap, progressive PIN lockout, headers."""
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.database import SessionLocal
from app.models import User, utcnow
from app.security_middleware import SecurityMiddleware


def _mini_app(max_bytes=100, per_min=3):
    app = FastAPI()

    @app.post("/api/v1/auth/pin/login")
    async def login():
        return {"ok": True}

    @app.post("/api/v1/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    app.add_middleware(SecurityMiddleware, max_bytes=max_bytes, auth_per_minute=per_min)
    return TestClient(app)


def test_auth_rate_limit_per_ip():
    c = _mini_app()
    assert [c.post("/api/v1/auth/pin/login").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert c.post("/api/v1/echo", content=b"x").status_code == 200        # other routes unaffected


def test_streaming_body_cap_without_content_length():
    c = _mini_app(max_bytes=100)

    def gen():
        for _ in range(10):
            yield b"x" * 50                                          # chunked, no Content-Length
    assert c.post("/api/v1/echo", content=gen()).status_code == 413
    assert c.post("/api/v1/echo", content=b"x" * 50).json() == {"n": 50}


def test_security_headers_on_api_and_static(anon):
    for path in ("/api/v1/version", "/"):
        r = anon.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "script-src 'self'" in r.headers["content-security-policy"]
    assert anon.get("/api/v1/version").headers["cache-control"] == "no-store"
    assert anon.get("/sw.js").headers["cache-control"] == "no-cache"


def test_progressive_pin_lockout(client):
    client.post("/api/v1/users", json={"phone": "0500000030", "name": "c", "role": "cashier", "pin": "4821"})
    login = lambda pin: client.post("/api/v1/auth/pin/login", json={"phone": "0500000030", "pin": pin}).status_code  # noqa: E731

    def unlock():
        with SessionLocal() as db:
            db.execute(update(User).where(User.phone == "+966500000030").values(locked_until=utcnow() - timedelta(seconds=1)))
            db.commit()

    def lock_minutes():
        with SessionLocal() as db:
            u = db.query(User).filter(User.phone == "+966500000030").one()
            lu = u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=utcnow().tzinfo)
            return round((lu - utcnow()).total_seconds() / 60)

    for _ in range(5):
        login("9999")
    assert lock_minutes() == 15
    unlock()
    for _ in range(5):
        login("9999")
    assert lock_minutes() == 30                                     # doubled
    unlock()
    assert login("4821") == 200                                     # success resets the counter


def test_no_secrets_or_stack_traces_leak(anon):
    r = anon.post("/api/v1/auth/otp/verify", json={"phone": "+966551234567", "code": "123456"})
    assert r.status_code == 401 and "Traceback" not in r.text and "secret" not in r.text.lower()
    assert anon.get("/openapi.json").status_code == 404 or "paths" not in anon.get("/openapi.json").text

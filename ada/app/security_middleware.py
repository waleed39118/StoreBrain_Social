"""HTTP hardening: security headers, streaming request-size cap, per-IP auth rate limit,
no-cache app shell. Implemented as pure ASGI middleware (no buffering, works with
streaming/chunked bodies that carry no Content-Length)."""
import json
import time
from collections import defaultdict, deque

from starlette.staticfiles import StaticFiles

# Everything is served from our own origin: no CDNs, no third-party scripts, no inline JS.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; font-src 'self'; worker-src 'self'; "
       "manifest-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'none'")
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class BodyTooLarge(Exception):
    pass


class SecurityMiddleware:
    AUTH_PREFIXES = ("/api/v1/auth/otp", "/api/v1/auth/pin", "/api/v1/setup/pairing")

    def __init__(self, app, max_bytes: int, auth_per_minute: int = 30) -> None:
        self.app, self.max_bytes, self.auth_per_minute = app, max_bytes, auth_per_minute
        self._hits: dict[str, deque] = defaultdict(deque)

    def _rate_limited(self, scope) -> bool:
        if scope["method"] != "POST" or not scope["path"].startswith(self.AUTH_PREFIXES):
            return False
        ip = (scope.get("client") or ("?", 0))[0]
        now, q = time.monotonic(), self._hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.auth_per_minute:
            return True
        q.append(now)
        if len(self._hits) > 10_000:                 # bound memory under spoofed-IP floods
            self._hits.clear()
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            return await _json(send, 413, "Request too large")
        if self._rate_limited(scope):
            return await _json(send, 429, "Too many attempts; try again in a minute")

        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLarge
            return msg

        is_api = scope["path"].startswith("/api/")
        started = False

        async def secure_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
                hdrs = [(k, v) for k, v in msg.get("headers", [])]
                present = {k.lower() for k, _ in hdrs}
                for k, v in HEADERS.items():
                    if k.lower().encode() not in present:
                        hdrs.append((k.lower().encode(), v.encode()))
                if is_api and b"cache-control" not in present:
                    hdrs.append((b"cache-control", b"no-store"))
                msg = {**msg, "headers": hdrs}
            await send(msg)

        try:
            await self.app(scope, limited_receive, secure_send)
        except BodyTooLarge:
            if not started:
                await _json(send, 413, "Request too large")


async def _json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    hdrs = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    hdrs += [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
    await send({"type": "http.response.start", "status": status, "headers": hdrs})
    await send({"type": "http.response.body", "body": body})


class AppShellFiles(StaticFiles):
    """Static PWA files; always revalidated so updates reach every till immediately."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        if path.endswith("sw.js"):
            resp.headers["Service-Worker-Allowed"] = "/"
        return resp

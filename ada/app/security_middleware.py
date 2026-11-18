"""HTTP hardening: strict security headers, request-size cap, no-cache for the app shell."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
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


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request, call_next):
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > self.max_bytes):
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class AppShellFiles(StaticFiles):
    """Static PWA files; always revalidated so updates reach every till immediately."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        if path.endswith("sw.js"):
            resp.headers["Service-Worker-Allowed"] = "/"
        return resp

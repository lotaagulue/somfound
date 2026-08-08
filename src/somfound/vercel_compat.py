"""Vercel-specific ASGI glue — kept out of main.py so local/Render behavior
is untouched by it.

Confirmed empirically (not from docs): Vercel's Python runtime, when a
request reaches the function via `vercel.json`'s catch-all rewrite, delivers
`scope["path"]` as the function's own address (`/api/index`) for *every*
request, not the original browsed URL — so plain FastAPI routing can't tell
`/` from `/report` from `/api/reports`. The documented workaround (Vercel
supports this pattern for passing route params to a function — see their
`destination: "/api/blog?slug=:slug"` example) is to have the rewrite append
the real path as a query parameter, then restore it here before the ASGI
app's own router sees the request.
"""

from urllib.parse import parse_qs, urlencode

ORIGINAL_PATH_PARAM = "__path"


class RestoreOriginalPathMiddleware:
    """Raw ASGI middleware (not `@app.middleware("http")`) because the path
    has to be fixed *before* routing decides which endpoint handles the
    request — that decision happens inside the app being wrapped here."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            query_string = scope.get("query_string", b"").decode("latin-1")
            params = parse_qs(query_string, keep_blank_values=True)
            original = params.pop(ORIGINAL_PATH_PARAM, None)
            if original:
                path = original[0]
                scope["path"] = path if path.startswith("/") else f"/{path}"
                scope["raw_path"] = scope["path"].encode("latin-1")
                scope["query_string"] = urlencode(params, doseq=True).encode("latin-1")
        await self.app(scope, receive, send)

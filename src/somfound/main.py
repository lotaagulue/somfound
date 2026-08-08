from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from somfound.db import engine, init_db
from somfound.paths import STATIC_DIR
from somfound.routers import api, moderation, pages, resources, sms, wallet
from somfound.seed import seed_demo_reports, seed_lgas, seed_reward_catalog


def _init_and_seed() -> None:
    """Idempotent: safe to call more than once (e.g. once per cold start on
    serverless hosts that don't reliably run ASGI lifespan events)."""
    init_db()
    with Session(engine) as session:
        lgas = seed_lgas(session)
        seed_demo_reports(session, lgas)
        seed_reward_catalog(session)


_init_and_seed()

app = FastAPI(title="Somfound")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/sw.js")
def service_worker() -> FileResponse:
    """Served from the root path (not /static/sw.js) so its default scope
    covers the whole origin — a service worker can only control paths at or
    below the directory its own script lives in."""
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


app.include_router(pages.router)
app.include_router(moderation.router)
app.include_router(resources.router)
app.include_router(wallet.router)
app.include_router(api.router)
app.include_router(sms.router)


@app.middleware("http")
async def _no_edge_cache(request: Request, call_next):
    """Every page here can change between requests (new reports, moderation
    decisions) — never let Vercel's (or any) edge cache serve a stale one.
    This also fixed a real production bug: without an explicit Cache-Control,
    Vercel's edge was caching responses keyed by the rewrite *destination*
    rather than the original request path, so every distinct URL served the
    same frozen response from whichever request happened to populate the
    cache first."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Same status code/shape as FastAPI's default, plus the path it actually
    routed on — cheap and permanently useful for diagnosing host-specific
    routing quirks (e.g. a reverse-proxy rewrite not preserving the path)
    without adding a temporary debug-only route."""
    content = {"detail": exc.detail}
    if exc.status_code == 404:
        content["requested_path"] = request.url.path
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


def main() -> None:
    import uvicorn

    uvicorn.run("somfound.main:app", host="0.0.0.0", port=8000, reload=True)

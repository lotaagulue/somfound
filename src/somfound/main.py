from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from somfound.db import engine, init_db
from somfound.paths import STATIC_DIR
from somfound.routers import api, moderation, pages, sms
from somfound.seed import seed_demo_reports, seed_villages


def _init_and_seed() -> None:
    """Idempotent: safe to call more than once (e.g. once per cold start on
    serverless hosts that don't reliably run ASGI lifespan events)."""
    init_db()
    with Session(engine) as session:
        villages = seed_villages(session)
        seed_demo_reports(session, villages)


_init_and_seed()

app = FastAPI(title="Somfound")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(pages.router)
app.include_router(moderation.router)
app.include_router(api.router)
app.include_router(sms.router)


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

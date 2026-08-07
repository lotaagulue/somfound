from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from somfound.db import engine, init_db
from somfound.routers import api, moderation, pages, sms
from somfound.seed import seed_demo_reports, seed_villages


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        villages = seed_villages(session)
        seed_demo_reports(session, villages)
    yield


app = FastAPI(title="Somfound", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/somfound/static"), name="static")

app.include_router(pages.router)
app.include_router(moderation.router)
app.include_router(api.router)
app.include_router(sms.router)


def main() -> None:
    import uvicorn

    uvicorn.run("somfound.main:app", host="0.0.0.0", port=8000, reload=True)

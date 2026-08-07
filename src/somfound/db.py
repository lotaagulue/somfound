"""Database engine/session setup.

SQLite by default so the demo runs with zero external services. Set
DATABASE_URL to point at Postgres (or anything SQLAlchemy supports) later
without touching application code.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

# Vercel's serverless filesystem is read-only except /tmp — fall back there
# automatically so the same code works locally, on Render, and on Vercel.
_default_sqlite = "sqlite:////tmp/somfound.db" if os.environ.get("VERCEL") else "sqlite:///./somfound.db"
DATABASE_URL = os.environ.get("DATABASE_URL", _default_sqlite)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

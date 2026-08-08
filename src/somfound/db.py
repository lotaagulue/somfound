"""Database engine/session setup.

SQLite by default so the demo runs with zero external services. Set
DATABASE_URL to point at Postgres (e.g. Supabase) instead — see README §"Using
Supabase for storage" — without touching application code beyond this file.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

# Vercel's serverless filesystem is read-only except /tmp — fall back there
# automatically so the same code works locally, on Render, and on Vercel.
def normalize_database_url(url: str) -> str:
    """SQLAlchemy dropped support for the bare "postgres://" scheme that
    Supabase (and others, e.g. Heroku) still hand out — normalize it rather
    than making every deployer remember to edit their connection string."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


_default_sqlite = "sqlite:////tmp/somfound.db" if os.environ.get("VERCEL") else "sqlite:///./somfound.db"
DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", _default_sqlite))

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
# Supabase's connection pooler (Supavisor, port 6543) — the right choice for
# serverless, since it handles many short-lived connections without
# exhausting Postgres's direct connection limit — runs in transaction mode,
# which does not support server-side prepared statements. Disabling
# SQLAlchemy's statement cache keeps this safe whether or not the pooler is
# actually in front of the connection.
_engine_kwargs = {} if _is_sqlite else {"execution_options": {"compiled_cache": None}}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

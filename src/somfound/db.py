"""Database engine/session setup.

SQLite by default so the demo runs with zero external services. Set
DATABASE_URL to point at Postgres (e.g. Supabase) instead — see README §"Using
Supabase for storage" — without touching application code beyond this file.
"""

import os
from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine


def normalize_database_url(url: str) -> str:
    """SQLAlchemy dropped support for the bare "postgres://" scheme that
    Supabase (and others, e.g. Heroku) still hand out — normalize it rather
    than making every deployer remember to edit their connection string."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


# Vercel's serverless filesystem is read-only except /tmp — fall back there
# automatically so the same code works locally, on Render, and on Vercel.
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


def _run_additive_migrations() -> None:
    """`create_all()` only creates *missing* tables — it never alters ones
    that already exist. There's no Alembic set up yet, so handle the handful
    of additive (never destructive) column changes by hand here. Safe to run
    on every startup: a fresh DB already has every column current models
    define, so each check below is a no-op for it.

    Currently:
    - Report.village_id -> Report.lga_id (villages -> LGAs rename). The old
      `village_id` column and `village` table are left in place rather than
      dropped — harmless orphaned data on a demo-stage DB, and dropping
      columns/tables is exactly the kind of irreversible step not worth
      taking without a real migration tool backing it.
    - Report.confirmations_count (Phase C: peer confirmations), default 0
      so existing rows don't end up NULL.
    - Report.wallet_id, Report.points_awarded (Phase C: reward wallets).
      create_all() already created the new `wallet` table by the time this
      runs, but these are added as plain nullable/defaulted columns with no
      DB-level FK constraint (consistent with lga_id above) — an old report
      predating this feature just has wallet_id=NULL, points_awarded=0,
      which is exactly correct: it never had a wallet to award points to.
    - Report.submission_token (resubmission/idempotency guard for the web
      report form — see models.py's docstring on the field), default '' so
      existing rows (which never had a token to begin with) just aren't
      replay-matchable, which is correct: nothing to replay.
    - Report.summary (AI-generated map-popup summary — see models.py's
      docstring on the field), default '' so existing rows just show their
      full description on the map, same as before this existed.
    """
    inspector = inspect(engine)
    if "report" not in inspector.get_table_names():
        return  # fresh DB — create_all() just built the current schema already
    columns = {c["name"] for c in inspector.get_columns("report")}
    with engine.begin() as conn:
        if "lga_id" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN lga_id INTEGER"))
        if "confirmations_count" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN confirmations_count INTEGER DEFAULT 0"))
        if "wallet_id" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN wallet_id INTEGER"))
        if "points_awarded" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN points_awarded INTEGER DEFAULT 0"))
        if "submission_token" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN submission_token VARCHAR DEFAULT ''"))
        if "summary" not in columns:
            conn.execute(text("ALTER TABLE report ADD COLUMN summary VARCHAR DEFAULT ''"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _run_additive_migrations()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

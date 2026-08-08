"""JSON endpoints consumed by the map's JS."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from somfound import crud
from somfound.db import DATABASE_URL, get_session
from somfound.models import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    URGENCY_COLORS,
    URGENCY_LABELS,
    Category,
    Urgency,
)

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    """Cheap liveness/config check — confirms the app booted, the DB is
    reachable, and (without leaking credentials) which DB backend is in use.
    Useful when debugging a deploy: hit /api/health before assuming routing
    is broken vs. the app never having started."""
    db_kind = "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql"
    return {"status": "ok", "db": db_kind, "villages_seeded": len(crud.list_villages(session))}


@router.get("/reports")
def api_list_reports(
    category: Category | None = None,
    urgency: Urgency | None = None,
    since_days: int | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    reports = crud.list_published_reports(
        session, category=category, urgency=urgency, since_days=since_days
    )
    return [
        {
            "id": r.id,
            "category": r.category.value,
            "category_label": CATEGORY_LABELS[r.category],
            "icon": CATEGORY_ICONS[r.category],
            "urgency": r.urgency.value,
            "urgency_label": URGENCY_LABELS[r.urgency],
            "color": URGENCY_COLORS[r.urgency],
            "status": r.status.value,
            "description": r.description,
            "lat": r.lat,
            "lon": r.lon,
            "source_channel": r.source_channel.value,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]

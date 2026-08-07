"""JSON endpoints consumed by the map's JS."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from somfound import crud
from somfound.db import get_session
from somfound.models import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    URGENCY_COLORS,
    URGENCY_LABELS,
    Category,
    Urgency,
)

router = APIRouter(prefix="/api", tags=["api"])


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

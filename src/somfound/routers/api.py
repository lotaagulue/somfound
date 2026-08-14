"""JSON endpoints consumed by the map's JS."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session

from somfound import crud
from somfound.db import DATABASE_URL, get_session
from somfound.models import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    RESOLVED_COLOR,
    URGENCY_COLORS,
    URGENCY_LABELS,
    Category,
    Status,
    Urgency,
)
from somfound.session import get_session_hash

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    """Cheap liveness/config check — confirms the app booted, the DB is
    reachable, and (without leaking credentials) which DB backend is in use.
    Useful when debugging a deploy: hit /api/health before assuming routing
    is broken vs. the app never having started."""
    db_kind = "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql"
    return {"status": "ok", "db": db_kind, "lgas_seeded": len(crud.list_lgas(session))}


@router.get("/reports")
def api_list_reports(
    category: Category | None = None,
    urgency: Urgency | None = None,
    since_days: int | None = None,
    include_resolved: bool = False,
    session: Session = Depends(get_session),
) -> list[dict]:
    reports = crud.list_published_reports(
        session,
        category=category,
        urgency=urgency,
        since_days=since_days,
        include_resolved=include_resolved,
    )
    return [
        {
            "id": r.id,
            "category": r.category.value,
            "category_label": CATEGORY_LABELS[r.category],
            "icon": CATEGORY_ICONS[r.category],
            "urgency": r.urgency.value,
            "urgency_label": URGENCY_LABELS[r.urgency],
            # A resolved report is deliberately greyed out regardless of its
            # original urgency — it shouldn't keep reading as "live" (see
            # README §4, this is literally what "Resolved" is supposed to do).
            "color": RESOLVED_COLOR if r.status == Status.RESOLVED else URGENCY_COLORS[r.urgency],
            "status": r.status.value,
            "description": r.description,
            # AI-generated, short — "" if summarization was skipped (short
            # description, no provider configured, call failed) or the
            # report predates this feature. The map falls back to showing
            # `description` whenever this is empty.
            "summary": r.summary,
            "lat": r.lat,
            "lon": r.lon,
            "source_channel": r.source_channel.value,
            "created_at": r.created_at.isoformat(),
            "confirmations_count": r.confirmations_count,
        }
        for r in reports
    ]


@router.post("/reports/{report_id}/confirm")
def confirm_report(
    report_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Anonymous peer confirmation — "I can confirm this happened/is still
    true." One per browser per report (see somfound/session.py); no login,
    no phone number, just enough friction to stop trivial spam-clicking.
    Only published reports are confirmable — a pending/rejected report isn't
    public yet, and a resolved one is already de-emphasized on the map."""
    report = crud.get_report(session, report_id)
    if report is None or report.status != Status.PUBLISHED:
        raise HTTPException(status_code=404, detail="Report not found")

    session_hash = get_session_hash(request, response)
    report, was_new = crud.confirm_report(session, report, session_hash=session_hash)
    return {"confirmations_count": report.confirmations_count, "already_confirmed": not was_new}

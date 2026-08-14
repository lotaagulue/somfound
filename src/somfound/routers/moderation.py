"""Moderator queue — everything here requires HTTP Basic auth. Nothing a
reporter submits reaches the public map until a moderator approves it."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from somfound import crud
from somfound.auth import require_moderator
from somfound.db import get_session
from somfound.llm_classifier import summarize_description
from somfound.models import CATEGORY_LABELS, URGENCY_LABELS, Report, Status
from somfound.paths import TEMPLATES_DIR

router = APIRouter(prefix="/moderate", tags=["moderation"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("")
def moderation_queue(
    request: Request,
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    pending = crud.list_pending_reports(session)
    published = list(
        session.exec(
            select(Report).where(Report.status == Status.PUBLISHED).order_by(Report.published_at.desc())
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "moderate.html",
        {
            "pending": pending,
            "published": published,
            "category_labels": CATEGORY_LABELS,
            "urgency_labels": URGENCY_LABELS,
        },
    )


@router.post("/{report_id}/{action}")
def moderate_action(
    report_id: int,
    action: str,
    notes: str = Form(""),
    award_points: int = Form(0),
    session: Session = Depends(get_session),
    _moderator: str = Depends(require_moderator),
):
    report = crud.get_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if action not in {"approve", "reject", "resolve"}:
        raise HTTPException(status_code=400, detail="Unknown action")

    # Only ever generated for what's actually about to go public, and only
    # once — never re-summarized on subsequent moderation actions or map
    # loads. See llm_classifier.summarize_description for the graceful-
    # fallback behavior (None if too short to bother, no provider
    # configured, or the call failed — the map just shows the full
    # description in that case).
    summary = summarize_description(report.description) if action == "approve" else None

    crud.moderate_report(
        session, report, action=action, notes=notes, award_points=award_points, summary=summary
    )
    return RedirectResponse(url="/moderate", status_code=303)

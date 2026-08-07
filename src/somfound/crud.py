"""Thin data-access helpers around the SQLModel session."""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from somfound.models import Category, Report, SourceChannel, Status, Urgency, Village


def hash_reporter_contact(raw: str) -> str:
    """Never store a raw phone number — only a stable, non-reversible hash of it."""
    if not raw:
        return ""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()[:16]


def list_villages(session: Session) -> list[Village]:
    return list(session.exec(select(Village).order_by(Village.name)).all())


def create_report(
    session: Session,
    *,
    category: Category,
    urgency: Urgency,
    description: str,
    lat: float,
    lon: float,
    source_channel: SourceChannel,
    village_id: int | None = None,
    location_hint: str = "",
    reporter_contact: str = "",
) -> Report:
    report = Report(
        category=category,
        urgency=urgency,
        status=Status.PENDING,
        description=description,
        lat=lat,
        lon=lon,
        village_id=village_id,
        location_hint=location_hint,
        source_channel=source_channel,
        reporter_ref=hash_reporter_contact(reporter_contact),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_published_reports(
    session: Session,
    *,
    category: Category | None = None,
    urgency: Urgency | None = None,
    since_days: int | None = None,
) -> list[Report]:
    statement = select(Report).where(Report.status.in_([Status.PUBLISHED, Status.RESOLVED]))
    if category:
        statement = statement.where(Report.category == category)
    if urgency:
        statement = statement.where(Report.urgency == urgency)
    if since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        statement = statement.where(Report.created_at >= cutoff)
    statement = statement.order_by(Report.created_at.desc())
    return list(session.exec(statement).all())


def list_pending_reports(session: Session) -> list[Report]:
    statement = (
        select(Report).where(Report.status == Status.PENDING).order_by(Report.created_at.asc())
    )
    return list(session.exec(statement).all())


def get_report(session: Session, report_id: int) -> Report | None:
    return session.get(Report, report_id)


def moderate_report(
    session: Session,
    report: Report,
    *,
    action: str,
    notes: str = "",
    category: Category | None = None,
    urgency: Urgency | None = None,
) -> Report:
    now = datetime.now(timezone.utc)
    if category:
        report.category = category
    if urgency:
        report.urgency = urgency
    if notes:
        report.moderator_notes = notes

    if action == "approve":
        report.status = Status.PUBLISHED
        report.published_at = now
    elif action == "reject":
        report.status = Status.REJECTED
    elif action == "resolve":
        report.status = Status.RESOLVED
        report.resolved_at = now
    else:
        raise ValueError(f"Unknown moderation action: {action}")

    session.add(report)
    session.commit()
    session.refresh(report)
    return report

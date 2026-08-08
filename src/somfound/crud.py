"""Thin data-access helpers around the SQLModel session."""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from somfound.models import (
    LGA,
    Category,
    Report,
    ReportConfirmation,
    Resource,
    ResourceStatus,
    ResourceType,
    SourceChannel,
    Status,
    Urgency,
)


def hash_reporter_contact(raw: str) -> str:
    """Never store a raw phone number — only a stable, non-reversible hash of it."""
    if not raw:
        return ""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()[:16]


def list_lgas(session: Session) -> list[LGA]:
    return list(session.exec(select(LGA).order_by(LGA.state, LGA.name)).all())


def create_report(
    session: Session,
    *,
    category: Category,
    urgency: Urgency,
    description: str,
    lat: float,
    lon: float,
    source_channel: SourceChannel,
    lga_id: int | None = None,
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
        lga_id=lga_id,
        location_hint=location_hint,
        source_channel=source_channel,
        reporter_ref=hash_reporter_contact(reporter_contact),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


# --- Resources (first-aid kit boxes, etc.) — moderator-managed, no public submission ---


def list_resources(session: Session) -> list[Resource]:
    return list(session.exec(select(Resource).order_by(Resource.created_at.desc())).all())


def create_resource(
    session: Session,
    *,
    resource_type: ResourceType,
    status: ResourceStatus,
    lga_id: int | None,
    lat: float,
    lon: float,
    notes: str = "",
) -> Resource:
    resource = Resource(
        resource_type=resource_type, status=status, lga_id=lga_id, lat=lat, lon=lon, notes=notes
    )
    session.add(resource)
    session.commit()
    session.refresh(resource)
    return resource


def get_resource(session: Session, resource_id: int) -> Resource | None:
    return session.get(Resource, resource_id)


def update_resource_status(
    session: Session, resource: Resource, *, status: ResourceStatus, notes: str = ""
) -> Resource:
    resource.status = status
    if notes:
        resource.notes = notes
    resource.updated_at = datetime.now(timezone.utc)
    session.add(resource)
    session.commit()
    session.refresh(resource)
    return resource


def list_published_reports(
    session: Session,
    *,
    category: Category | None = None,
    urgency: Urgency | None = None,
    since_days: int | None = None,
    include_resolved: bool = False,
) -> list[Report]:
    statuses = [Status.PUBLISHED, Status.RESOLVED] if include_resolved else [Status.PUBLISHED]
    statement = select(Report).where(Report.status.in_(statuses))
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


# --- Peer confirmations ---


def confirm_report(session: Session, report: Report, *, session_hash: str) -> tuple[Report, bool]:
    """Returns (report, was_new). Idempotent: confirming twice from the same
    anonymous session just returns the current state, doesn't double-count."""
    already = session.exec(
        select(ReportConfirmation).where(
            ReportConfirmation.report_id == report.id,
            ReportConfirmation.session_hash == session_hash,
        )
    ).first()
    if already:
        return report, False

    session.add(ReportConfirmation(report_id=report.id, session_hash=session_hash))
    report.confirmations_count += 1
    session.add(report)
    session.commit()
    session.refresh(report)
    return report, True

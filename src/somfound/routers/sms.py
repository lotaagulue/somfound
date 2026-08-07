"""Inbound SMS webhook, compatible with Africa's Talking's callback format
(https://developers.africastalking.com/docs/sms/callback) — including their
free sandbox simulator, so this can be exercised at zero cost.
"""

from fastapi import APIRouter, Depends, Form
from sqlmodel import Session, func, select

from somfound import crud
from somfound.db import get_session
from somfound.models import Report, SmsInbound, SourceChannel, Status
from somfound.sms_client import send_confirmation
from somfound.sms_parser import parse_sms

router = APIRouter(prefix="/sms", tags=["sms"])

MAX_PENDING_PER_REPORTER = 3  # light per-phone rate limit against spam/abuse


@router.post("/inbound")
def inbound_sms(
    from_: str = Form(..., alias="from"),
    text: str = Form(...),
    session: Session = Depends(get_session),
) -> dict:
    villages = crud.list_villages(session)
    parsed = parse_sms(text, villages)
    reporter_ref = crud.hash_reporter_contact(from_)

    pending_count = session.exec(
        select(func.count())
        .select_from(Report)
        .where(Report.reporter_ref == reporter_ref, Report.status == Status.PENDING)
    ).one()

    linked_report_id = None
    if pending_count < MAX_PENDING_PER_REPORTER:
        report = crud.create_report(
            session,
            category=parsed.category,
            urgency=parsed.urgency,
            description=parsed.description,
            lat=parsed.village.lat if parsed.village else 0.0,
            lon=parsed.village.lon if parsed.village else 0.0,
            village_id=parsed.village.id if parsed.village else None,
            location_hint="" if parsed.village else text,
            source_channel=SourceChannel.SMS,
            reporter_contact=from_,
        )
        linked_report_id = report.id
        reply = "Got it, thanks — under review." if parsed.keyword_matched else (
            "Got it, thanks — a moderator will review and categorize this shortly."
        )
    else:
        reply = "You have several reports pending review already — please wait before sending more."

    session.add(
        SmsInbound(
            from_phone_hash=reporter_ref,
            raw_text=text,
            parsed_category=parsed.category.value,
            parsed_urgency=parsed.urgency.value,
            linked_report_id=linked_report_id,
        )
    )
    session.commit()

    send_confirmation(from_, reply)
    return {"status": "ok", "report_id": linked_report_id}

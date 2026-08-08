"""Core inbound-SMS handling, shared by the real webhook (`routers/sms.py`,
for whenever a real SMS gateway is wired up) and the in-app SMS simulator
(`/sms/simulate`) used to demo the pipeline without one."""

from dataclasses import dataclass

from sqlmodel import Session, func, select

from somfound import crud
from somfound.models import CATEGORY_LABELS, URGENCY_LABELS, Category, Report, SmsInbound, SourceChannel, Status, Urgency
from somfound.sms_parser import parse_sms

MAX_PENDING_PER_REPORTER = 3  # light per-phone rate limit against spam/abuse


@dataclass
class SmsOutcome:
    report_id: int | None
    category: Category
    urgency: Urgency
    village_name: str | None
    keyword_matched: bool
    rate_limited: bool
    reply: str

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS[self.category]

    @property
    def urgency_label(self) -> str:
        return URGENCY_LABELS[self.urgency]


def process_inbound_sms(session: Session, *, from_phone: str, text: str) -> SmsOutcome:
    villages = crud.list_villages(session)
    parsed = parse_sms(text, villages)
    reporter_ref = crud.hash_reporter_contact(from_phone)

    pending_count = session.exec(
        select(func.count())
        .select_from(Report)
        .where(Report.reporter_ref == reporter_ref, Report.status == Status.PENDING)
    ).one()

    rate_limited = pending_count >= MAX_PENDING_PER_REPORTER
    linked_report_id = None

    if not rate_limited:
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
            reporter_contact=from_phone,
        )
        linked_report_id = report.id
        reply = (
            "Got it, thanks — under review."
            if parsed.keyword_matched
            else "Got it, thanks — a moderator will review and categorize this shortly."
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

    return SmsOutcome(
        report_id=linked_report_id,
        category=parsed.category,
        urgency=parsed.urgency,
        village_name=parsed.village.name if parsed.village else None,
        keyword_matched=parsed.keyword_matched,
        rate_limited=rate_limited,
        reply=reply,
    )

"""Core inbound-SMS handling, shared by the real webhook (`routers/sms.py`,
for whenever a real SMS gateway is wired up) and the in-app SMS simulator
(`/sms/simulate`) used to demo the pipeline without one."""

from dataclasses import dataclass

from sqlmodel import Session

from somfound import crud
from somfound.models import CATEGORY_LABELS, URGENCY_LABELS, Category, SmsInbound, SourceChannel, Urgency
from somfound.sms_parser import parse_sms


@dataclass
class SmsOutcome:
    report_id: int | None
    category: Category
    urgency: Urgency
    lga_name: str | None
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
    lgas = crud.list_lgas(session)
    parsed = parse_sms(text, lgas)
    reporter_ref = crud.hash_reporter_contact(from_phone)

    pending_count = crud.count_pending_reports(session, reporter_ref)
    rate_limited = pending_count >= crud.MAX_PENDING_PER_REPORTER
    linked_report_id = None

    if not rate_limited:
        # SMS always has a phone number, so this always resolves to a
        # phone-linked wallet — no separate wallet code to remember, the
        # same phone number always gets back into the same wallet.
        wallet = crud.get_or_create_wallet_by_phone(session, reporter_ref)
        report = crud.create_report(
            session,
            category=parsed.category,
            urgency=parsed.urgency,
            description=parsed.description,
            lat=parsed.lga.lat if parsed.lga else 0.0,
            lon=parsed.lga.lon if parsed.lga else 0.0,
            lga_id=parsed.lga.id if parsed.lga else None,
            location_hint="" if parsed.lga else text,
            source_channel=SourceChannel.SMS,
            reporter_contact=from_phone,
            wallet_id=wallet.id,
        )
        linked_report_id = report.id
        base_reply = (
            "Got it, thanks — under review."
            if parsed.keyword_matched
            else "Got it, thanks — a moderator will review and categorize this shortly."
        )
        reply = f"{base_reply} Verified reports can earn reward points — check yours at /wallet with this phone number."
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
        lga_name=parsed.lga.name if parsed.lga else None,
        keyword_matched=parsed.keyword_matched,
        rate_limited=rate_limited,
        reply=reply,
    )

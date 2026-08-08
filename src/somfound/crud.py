"""Thin data-access helpers around the SQLModel session."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, func, select

from somfound.models import (
    LGA,
    Category,
    RedemptionRequest,
    RedemptionStatus,
    Report,
    ReportConfirmation,
    Resource,
    ResourceStatus,
    ResourceType,
    RewardOption,
    SourceChannel,
    Status,
    Urgency,
    Wallet,
)

# Excludes visually ambiguous characters (0/O, 1/I/L) — this gets read back
# over the phone or typed from a handwritten note, so avoid characters people
# routinely mistype/misread against each other.
_WALLET_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Shared spam/abuse guard for both inbound channels (SMS in sms_service.py,
# web in routers/pages.py): once a reporter (by phone, or by IP for
# anonymous web submissions — see Report.reporter_ref) has this many reports
# still sitting in PENDING, further submissions are blocked until a
# moderator clears some of the backlog. Self-resets as the queue is worked,
# not a hard ban. Started at 3 (too tight for normal real usage), raised to
# 10, raised again to 100 ahead of a live audience demo — a room full of
# people on one shared venue WiFi all share this bucket (anonymous
# submissions fall back to a hash of the IP), and spam risk during a
# supervised in-person demo is effectively zero, so there's no real downside
# to generous headroom here.
MAX_PENDING_PER_REPORTER = 100


def hash_reporter_contact(raw: str) -> str:
    """Never store a raw phone number — only a stable, non-reversible hash of it.
    Also reused to hash a client IP for rate-limiting anonymous web reports
    (see routers/pages.py) — it's a generic string hasher, nothing here is
    phone-specific."""
    if not raw:
        return ""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()[:16]


def list_lgas(session: Session) -> list[LGA]:
    return list(session.exec(select(LGA).order_by(LGA.state, LGA.name)).all())


def count_pending_reports(session: Session, reporter_ref: str) -> int:
    """How many PENDING reports currently exist for this reporter_ref — the
    basis of the per-reporter rate limit shared by SMS and web."""
    return session.exec(
        select(func.count())
        .select_from(Report)
        .where(Report.reporter_ref == reporter_ref, Report.status == Status.PENDING)
    ).one()


def find_report_by_submission_token(session: Session, submission_token: str) -> Report | None:
    """A blank token never matches anything (see Report.submission_token's
    docstring) — every row defaults to '', so bailing out early here avoids
    an empty-token submission accidentally "replaying" an unrelated old
    report."""
    if not submission_token:
        return None
    return session.exec(select(Report).where(Report.submission_token == submission_token)).first()


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
    reporter_ref: str | None = None,
    wallet_id: int | None = None,
    submission_token: str = "",
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
        # Callers that already have a hashed identity (e.g. the web form's
        # rate-limit key, which may be an IP hash rather than a phone hash)
        # pass reporter_ref directly; otherwise it's derived from
        # reporter_contact as before.
        reporter_ref=reporter_ref if reporter_ref is not None else hash_reporter_contact(reporter_contact),
        wallet_id=wallet_id,
        submission_token=submission_token,
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
    award_points: int = 0,
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
        # Reward-worthy tips (per the business plan's anonymous tip reward
        # system): a moderator can award points on approval, credited to
        # whichever wallet this report is linked to. Only ever set once —
        # re-approving something already published isn't a normal flow, but
        # if it happened, this avoids silently double-crediting a wallet.
        if award_points > 0 and report.points_awarded == 0:
            report.points_awarded = award_points
            if report.wallet_id is not None:
                wallet = session.get(Wallet, report.wallet_id)
                if wallet is not None:
                    wallet.points_balance += award_points
                    session.add(wallet)
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


# --- Reward wallets ---


def _generate_wallet_code(session: Session, length: int = 8) -> str:
    while True:
        code = "".join(secrets.choice(_WALLET_CODE_ALPHABET) for _ in range(length))
        if not session.exec(select(Wallet).where(Wallet.wallet_code == code)).first():
            return code


def create_anonymous_wallet(session: Session) -> Wallet:
    wallet = Wallet(wallet_code=_generate_wallet_code(session))
    session.add(wallet)
    session.commit()
    session.refresh(wallet)
    return wallet


def get_or_create_wallet_by_phone(session: Session, phone_hash: str) -> Wallet:
    existing = session.exec(select(Wallet).where(Wallet.phone_hash == phone_hash)).first()
    if existing:
        return existing
    wallet = Wallet(wallet_code=_generate_wallet_code(session), phone_hash=phone_hash)
    session.add(wallet)
    session.commit()
    session.refresh(wallet)
    return wallet


def resolve_wallet_for_report(
    session: Session, *, wallet_code: str = "", reporter_contact: str = ""
) -> Wallet:
    """Every report gets a wallet, so every reporter has somewhere for
    reward points to land, even if they never ask for it:
    1. An explicit wallet code they already have wins, if it's valid.
    2. Otherwise, a phone number gets them a stable wallet they can return
       to just by giving the same phone number again — no code to remember.
    3. Otherwise, a brand new anonymous wallet, whose code is shown exactly
       once, at submission time — there's no other way back into it."""
    wallet_code = wallet_code.strip().upper()
    if wallet_code:
        existing = session.exec(select(Wallet).where(Wallet.wallet_code == wallet_code)).first()
        if existing:
            return existing

    phone_hash = hash_reporter_contact(reporter_contact)
    if phone_hash:
        return get_or_create_wallet_by_phone(session, phone_hash)

    return create_anonymous_wallet(session)


def find_wallet(session: Session, identifier: str) -> Wallet | None:
    """Looked up by wallet code OR by re-entering the phone number that
    created it — see Wallet's docstring."""
    identifier = identifier.strip()
    if not identifier:
        return None
    by_code = session.exec(select(Wallet).where(Wallet.wallet_code == identifier.upper())).first()
    if by_code:
        return by_code
    return session.exec(select(Wallet).where(Wallet.phone_hash == hash_reporter_contact(identifier))).first()


def list_active_reward_options(session: Session) -> list[RewardOption]:
    statement = (
        select(RewardOption).where(RewardOption.active == True).order_by(RewardOption.points_cost)  # noqa: E712
    )
    return list(session.exec(statement).all())


def get_reward_option(session: Session, reward_option_id: int) -> RewardOption | None:
    return session.get(RewardOption, reward_option_id)


def create_redemption(
    session: Session, wallet: Wallet, reward_option: RewardOption, *, contact_phone: str
) -> RedemptionRequest:
    """Points are deducted immediately, not on fulfillment — otherwise the
    same balance could back two simultaneous pending requests. Caller must
    have already checked wallet.points_balance >= reward_option.points_cost."""
    wallet.points_balance -= reward_option.points_cost
    session.add(wallet)

    redemption = RedemptionRequest(
        wallet_id=wallet.id,
        reward_option_id=reward_option.id,
        points_spent=reward_option.points_cost,
        contact_phone=contact_phone,
    )
    session.add(redemption)
    session.commit()
    session.refresh(redemption)
    return redemption


def list_redemptions(
    session: Session, *, status: RedemptionStatus | None = None, wallet_id: int | None = None
) -> list[RedemptionRequest]:
    statement = select(RedemptionRequest).order_by(RedemptionRequest.requested_at.asc())
    if status:
        statement = statement.where(RedemptionRequest.status == status)
    if wallet_id:
        statement = statement.where(RedemptionRequest.wallet_id == wallet_id)
    return list(session.exec(statement).all())


def get_redemption(session: Session, redemption_id: int) -> RedemptionRequest | None:
    return session.get(RedemptionRequest, redemption_id)


def resolve_redemption(
    session: Session, redemption: RedemptionRequest, *, status: RedemptionStatus, notes: str = ""
) -> RedemptionRequest:
    """FULFILLED just records it happened (delivery itself is manual/out-of-
    band — see RedemptionRequest.contact_phone). CANCELLED refunds the
    points back to the wallet, since they were deducted at request time."""
    if status == RedemptionStatus.CANCELLED and redemption.status != RedemptionStatus.CANCELLED:
        wallet = session.get(Wallet, redemption.wallet_id)
        if wallet is not None:
            wallet.points_balance += redemption.points_spent
            session.add(wallet)

    redemption.status = status
    if notes:
        redemption.admin_notes = notes
    if status == RedemptionStatus.FULFILLED:
        redemption.fulfilled_at = datetime.now(timezone.utc)

    session.add(redemption)
    session.commit()
    session.refresh(redemption)
    return redemption

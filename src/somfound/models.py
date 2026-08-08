"""Database models (SQLModel = SQLAlchemy table + Pydantic schema in one)."""

from datetime import datetime, timezone
from enum import StrEnum

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(StrEnum):
    CRIME_SAFETY = "crime_safety"
    INFRASTRUCTURE = "infrastructure"
    NEEDS_RESOURCES = "needs_resources"
    COMMUNITY_DEV = "community_dev"
    OTHER = "other"


class Urgency(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    INFORMATIONAL = "informational"


class Status(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class SourceChannel(StrEnum):
    WEB = "web"
    SMS = "sms"


CATEGORY_LABELS: dict[Category, str] = {
    Category.CRIME_SAFETY: "Crime & Safety",
    Category.INFRASTRUCTURE: "Infrastructure",
    Category.NEEDS_RESOURCES: "Needs & Resources",
    Category.COMMUNITY_DEV: "Community & Development",
    Category.OTHER: "Other",
}

CATEGORY_ICONS: dict[Category, str] = {
    Category.CRIME_SAFETY: "\U0001F6D1",  # stop sign
    Category.INFRASTRUCTURE: "\U0001F527",  # wrench
    Category.NEEDS_RESOURCES: "\U0001F4A7",  # droplet
    Category.COMMUNITY_DEV: "\U0001F3D7️",  # construction
    Category.OTHER: "❓",  # question mark
}

URGENCY_LABELS: dict[Urgency, str] = {
    Urgency.CRITICAL: "Critical",
    Urgency.HIGH: "High",
    Urgency.MODERATE: "Moderate",
    Urgency.INFORMATIONAL: "Informational",
}

# A validated status palette (good/warning/serious/critical) — chosen over a
# plain red/orange/yellow/blue ramp because that one fails colorblind and
# normal-vision separation between adjacent steps (checked with the dataviz
# skill's palette validator). Because "warning"/"serious" sit under 3:1
# contrast on a light surface by design, urgency must always be paired with
# a label or icon on screen — never color alone (see map legend + popups).
URGENCY_COLORS: dict[Urgency, str] = {
    Urgency.CRITICAL: "#d03b3b",
    Urgency.HIGH: "#ec835a",
    Urgency.MODERATE: "#fab219",
    Urgency.INFORMATIONAL: "#0ca30c",
}
PENDING_COLOR = "#9ca3af"  # grey, used for anything not yet published
RESOLVED_COLOR = "#9ca3af"  # same muted grey — a resolved report shouldn't still read as "live"


class LGA(SQLModel, table=True):
    """A Local Government Area — the reporting unit (states → LGAs), not
    individual villages. See seed.py for where the 95 real LGAs across the
    5 South-East states come from."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    state: str = Field(index=True)
    lat: float
    lon: float


class Report(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    category: Category
    urgency: Urgency
    status: Status = Status.PENDING
    description: str
    lat: float
    lon: float
    lga_id: int | None = Field(default=None, foreign_key="lga.id")
    location_hint: str = ""  # free-text place name when no LGA match (e.g. from SMS)
    source_channel: SourceChannel
    reporter_ref: str = ""  # hashed phone / anonymous session id, never raw phone
    moderator_notes: str = ""
    confirmations_count: int = 0  # peer confirmations from other reporters — see ReportConfirmation
    wallet_id: int | None = Field(default=None, foreign_key="wallet.id")
    points_awarded: int = 0  # set once, when a moderator approves — see Wallet
    # A random token minted when the web report form loads and echoed back on
    # submit — lets routers/pages.py detect a browser resubmitting the exact
    # same POST (e.g. hitting "back" past a no-store page and resending) and
    # replay the original confirmation instead of silently minting a second,
    # orphaned anonymous wallet. Blank for SMS/anything that isn't the web
    # form's own submit flow.
    submission_token: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: datetime | None = None
    resolved_at: datetime | None = None


class ResourceType(StrEnum):
    FIRST_AID_KIT = "first_aid_kit"
    # Room to grow — the business plan's other Q1 priority is first-aid kit
    # boxes specifically, but the shape (a moderator-managed physical
    # resource at an LGA location, with an install/condition status) applies
    # to future resource types too, not just this one.


class ResourceStatus(StrEnum):
    PLANNED = "planned"
    INSTALLED = "installed"
    NEEDS_RESTOCK = "needs_restock"
    DAMAGED = "damaged"


RESOURCE_TYPE_LABELS: dict[ResourceType, str] = {
    ResourceType.FIRST_AID_KIT: "First-Aid Kit Box",
}
RESOURCE_TYPE_ICONS: dict[ResourceType, str] = {
    ResourceType.FIRST_AID_KIT: "\U0001FA79",  # adhesive bandage
}
RESOURCE_STATUS_LABELS: dict[ResourceStatus, str] = {
    ResourceStatus.PLANNED: "Planned",
    ResourceStatus.INSTALLED: "Installed",
    ResourceStatus.NEEDS_RESTOCK: "Needs restock",
    ResourceStatus.DAMAGED: "Damaged",
}
# Reuses the same validated status-palette family as URGENCY_COLORS (see the
# comment above it) rather than inventing a new ramp — installed reads as
# "good" the same way informational urgency does.
RESOURCE_STATUS_COLORS: dict[ResourceStatus, str] = {
    ResourceStatus.PLANNED: "#9ca3af",
    ResourceStatus.INSTALLED: "#0ca30c",
    ResourceStatus.NEEDS_RESTOCK: "#fab219",
    ResourceStatus.DAMAGED: "#d03b3b",
}


class Resource(SQLModel, table=True):
    """A physical community resource the org installs and tracks — first-aid
    kit boxes today, per the business plan's other Q1 priority alongside the
    crime hotline. Moderator-managed only: unlike Report, there's no public
    submission path — installation is the org's own team's job."""

    id: int | None = Field(default=None, primary_key=True)
    resource_type: ResourceType
    status: ResourceStatus = ResourceStatus.PLANNED
    lga_id: int | None = Field(default=None, foreign_key="lga.id")
    lat: float
    lon: float
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ReportConfirmation(SQLModel, table=True):
    """One row per (report, anonymous session) that confirmed a report — the
    dedup record behind Report.confirmations_count. The unique constraint is
    the real guard against a double-count (e.g. a race between two
    near-simultaneous clicks); crud.confirm_report also checks first so the
    common case never even reaches the DB for an integrity error."""

    __table_args__ = (UniqueConstraint("report_id", "session_hash", name="uq_report_confirmation"),)

    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="report.id", index=True)
    session_hash: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class RedemptionStatus(StrEnum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


REDEMPTION_STATUS_LABELS: dict[RedemptionStatus, str] = {
    RedemptionStatus.PENDING: "Pending",
    RedemptionStatus.FULFILLED: "Fulfilled",
    RedemptionStatus.CANCELLED: "Cancelled",
}


class Wallet(SQLModel, table=True):
    """An anonymous points balance — the internal "currency" reporters earn
    when a moderator marks their verified report reward-worthy, redeemable
    for real rewards (gift cards, airtime — see RewardOption). No login: a
    wallet is identified by a human-typeable `wallet_code`, or by re-entering
    the same phone number that created it (see crud.find_wallet). Points
    accrue across every report linked to this wallet, not per-report — one
    wallet is meant to represent one (still anonymous) reporter over time.
    """

    id: int | None = Field(default=None, primary_key=True)
    wallet_code: str = Field(unique=True, index=True)
    phone_hash: str | None = Field(default=None, unique=True, index=True)  # optional, for phone-based lookup
    points_balance: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class RewardOption(SQLModel, table=True):
    """A catalog entry a wallet's points can be redeemed for. Seeded with
    illustrative examples (see seed.py) — replace with the org's actual
    partnerships (airtime aggregator, specific gift card vendors) before any
    real pilot; nothing here is a real payment integration."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    points_cost: int
    description: str = ""
    active: bool = True


class RedemptionRequest(SQLModel, table=True):
    """A wallet spending points on a RewardOption. Points are deducted
    immediately on request (not on fulfillment) to prevent double-spending
    the same balance across two pending requests; cancelling refunds them.

    contact_phone is the one deliberate exception to this app's "never store
    a raw phone number" rule (see Report.reporter_ref) — an actual reward
    (airtime, a gift card) has to be delivered to someone, which is
    fundamentally impossible from a one-way hash. Scoped as narrowly as
    possible: only here, only for active redemptions, never on Report or
    Wallet itself.
    """

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="wallet.id", index=True)
    reward_option_id: int = Field(foreign_key="rewardoption.id")
    points_spent: int  # snapshotted at request time, independent of later catalog price changes
    status: RedemptionStatus = RedemptionStatus.PENDING
    contact_phone: str  # plaintext by necessity — see docstring above
    admin_notes: str = ""
    requested_at: datetime = Field(default_factory=_utcnow)
    fulfilled_at: datetime | None = None


class SmsInbound(SQLModel, table=True):
    """Raw audit log of every inbound SMS, independent of whether parsing succeeded."""

    id: int | None = Field(default=None, primary_key=True)
    from_phone_hash: str
    raw_text: str
    parsed_category: str = ""
    parsed_urgency: str = ""
    linked_report_id: int | None = Field(default=None, foreign_key="report.id")
    received_at: datetime = Field(default_factory=_utcnow)

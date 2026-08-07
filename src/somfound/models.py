"""Database models (SQLModel = SQLAlchemy table + Pydantic schema in one)."""

from datetime import datetime, timezone
from enum import StrEnum

from sqlmodel import Field, SQLModel


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

URGENCY_COLORS: dict[Urgency, str] = {
    Urgency.CRITICAL: "#dc2626",  # red
    Urgency.HIGH: "#ea580c",  # orange
    Urgency.MODERATE: "#ca8a04",  # yellow/gold
    Urgency.INFORMATIONAL: "#2563eb",  # blue
}
PENDING_COLOR = "#9ca3af"  # grey, used for anything not yet published


class Village(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    ward: str = ""
    lga: str
    state: str = "Anambra"
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
    village_id: int | None = Field(default=None, foreign_key="village.id")
    location_hint: str = ""  # free-text place name when no village match (e.g. from SMS)
    source_channel: SourceChannel
    reporter_ref: str = ""  # hashed phone / anonymous session id, never raw phone
    moderator_notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    published_at: datetime | None = None
    resolved_at: datetime | None = None


class SmsInbound(SQLModel, table=True):
    """Raw audit log of every inbound SMS, independent of whether parsing succeeded."""

    id: int | None = Field(default=None, primary_key=True)
    from_phone_hash: str
    raw_text: str
    parsed_category: str = ""
    parsed_urgency: str = ""
    linked_report_id: int | None = Field(default=None, foreign_key="report.id")
    received_at: datetime = Field(default_factory=_utcnow)

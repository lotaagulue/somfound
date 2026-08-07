"""Freeform-SMS parsing.

Reporters text something like `WATER Umuoji borehole broken 3 days no fix`
with no rigid syntax required — the leading keyword (if recognized) sets the
category/urgency, any known village name mentioned anywhere in the message
is matched, and a few escalation words ("URGENT", "NOW", ...) bump the
urgency up a notch. Anything unrecognized still becomes a report — it just
lands in the queue as `other` / `moderate` for a moderator to reclassify.
"""

from dataclasses import dataclass

from somfound.models import Category, Urgency, Village

KEYWORD_MAP: dict[str, tuple[Category, Urgency]] = {
    "CRIME": (Category.CRIME_SAFETY, Urgency.HIGH),
    "SOS": (Category.CRIME_SAFETY, Urgency.CRITICAL),
    "HELP": (Category.CRIME_SAFETY, Urgency.HIGH),
    "WATER": (Category.NEEDS_RESOURCES, Urgency.HIGH),
    "MEDICAL": (Category.NEEDS_RESOURCES, Urgency.CRITICAL),
    "FOOD": (Category.NEEDS_RESOURCES, Urgency.HIGH),
    "ROAD": (Category.INFRASTRUCTURE, Urgency.MODERATE),
    "POWER": (Category.INFRASTRUCTURE, Urgency.MODERATE),
    "BRIDGE": (Category.INFRASTRUCTURE, Urgency.HIGH),
    "SCHOOL": (Category.COMMUNITY_DEV, Urgency.INFORMATIONAL),
    "NEWS": (Category.COMMUNITY_DEV, Urgency.INFORMATIONAL),
    "MARKET": (Category.COMMUNITY_DEV, Urgency.INFORMATIONAL),
}

ESCALATE_WORDS = {"URGENT", "EMERGENCY", "NOW", "ARMED"}

_URGENCY_ORDER = [Urgency.INFORMATIONAL, Urgency.MODERATE, Urgency.HIGH, Urgency.CRITICAL]


def _escalate(urgency: Urgency) -> Urgency:
    idx = _URGENCY_ORDER.index(urgency)
    return _URGENCY_ORDER[min(idx + 1, len(_URGENCY_ORDER) - 1)]


@dataclass
class ParsedSms:
    category: Category
    urgency: Urgency
    description: str
    keyword_matched: bool
    village: Village | None


def parse_sms(text: str, known_villages: list[Village]) -> ParsedSms:
    text = text.strip()
    tokens = text.split()

    keyword = tokens[0].upper() if tokens else ""
    mapping = KEYWORD_MAP.get(keyword)
    if mapping:
        category, urgency = mapping
        description = " ".join(tokens[1:]).strip() or text
    else:
        category, urgency = Category.OTHER, Urgency.MODERATE
        description = text

    if any(word in text.upper() for word in ESCALATE_WORDS):
        urgency = _escalate(urgency)

    lower_text = text.lower()
    village = next((v for v in known_villages if v.name.lower() in lower_text), None)

    return ParsedSms(
        category=category,
        urgency=urgency,
        description=description,
        keyword_matched=mapping is not None,
        village=village,
    )

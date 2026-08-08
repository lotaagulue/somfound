"""Freeform-text parsing shared by both inbound channels.

SMS (`parse_sms`): reporters text something like `WATER Nsukka borehole
broken 3 days no fix` with no rigid syntax required — the *leading* keyword
(if recognized) sets the category/urgency, any known LGA name mentioned
anywhere in the message is matched, and a few escalation words ("URGENT",
"NOW", ...) bump the urgency up a notch.

Web (`guess_category_urgency`): the report form lets someone just describe
what's happening in a normal sentence rather than lead with a keyword
("there was an armed robbery near the market"), so it scans the *whole*
sentence instead of just the first word — same keyword map, same escalation
words, just a different matching position. Both fall back to `other` /
`moderate` when nothing matches; a human (moderator) always gets a chance to
correct it before anything goes public either way.
"""

import re
from dataclasses import dataclass

from somfound.models import LGA, Category, Urgency

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


def _word_present(word: str, upper_text: str) -> bool:
    """Whole-word match, case-insensitive — a plain substring check would
    let e.g. "ROAD" false-positive inside "BROADBAND", or "ARMED" inside
    "FARMED"."""
    return re.search(rf"\b{re.escape(word)}\b", upper_text) is not None


def _is_escalated(text: str) -> bool:
    upper_text = text.upper()
    return any(_word_present(word, upper_text) for word in ESCALATE_WORDS)


def _first_keyword_match(text: str) -> tuple[Category, Urgency] | None:
    """The earliest (in reading order) recognized keyword anywhere in the
    text, whole-word matched. Used by guess_category_urgency — parse_sms
    only ever checks the leading token, which is cheaper and doesn't need
    this."""
    upper_text = text.upper()
    best_position = None
    best_mapping = None
    for keyword, mapping in KEYWORD_MAP.items():
        match = re.search(rf"\b{re.escape(keyword)}\b", upper_text)
        if match and (best_position is None or match.start() < best_position):
            best_position = match.start()
            best_mapping = mapping
    return best_mapping


@dataclass
class ParsedSms:
    category: Category
    urgency: Urgency
    description: str
    keyword_matched: bool
    lga: LGA | None


def parse_sms(text: str, known_lgas: list[LGA]) -> ParsedSms:
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

    if _is_escalated(text):
        urgency = _escalate(urgency)

    lower_text = text.lower()
    # Longest name first — defends against a shorter LGA name that happens to
    # also be a substring of a longer one grabbing the match instead (no
    # concrete collision in the current 95, but substring matching earns this
    # for free, so don't rely on list order being collision-free forever).
    lga = next(
        (lga for lga in sorted(known_lgas, key=lambda l: -len(l.name)) if lga.name.lower() in lower_text),
        None,
    )

    return ParsedSms(
        category=category,
        urgency=urgency,
        description=description,
        keyword_matched=mapping is not None,
        lga=lga,
    )


def guess_category_urgency(text: str) -> tuple[Category, Urgency, bool]:
    """Auto-suggest a category/urgency for the web report form, where people
    write a normal sentence rather than SMS's lead-with-a-keyword
    convention. Same keyword map and escalation words as parse_sms, just
    matched anywhere in the text (earliest match wins if more than one
    keyword appears) instead of only the first token. Falls back to
    (OTHER, MODERATE, False) — same as SMS's fallback — when nothing
    matches; a moderator still reviews every report before it's public
    either way, so this is a helpful default, not a final word."""
    mapping = _first_keyword_match(text)
    if mapping:
        category, urgency = mapping
        keyword_matched = True
    else:
        category, urgency = Category.OTHER, Urgency.MODERATE
        keyword_matched = False

    if _is_escalated(text):
        urgency = _escalate(urgency)

    return category, urgency, keyword_matched

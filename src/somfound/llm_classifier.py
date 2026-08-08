"""Optional LLM fallback for category/urgency classification on the web
report form — only used when sms_parser.guess_category_urgency() can't find
any keyword match at all (see routers/pages.py::submit_report). Keyword
matching stays the primary, fast, free path for the common case; this only
kicks in for the natural-language descriptions that don't hit any of the
~12 known keywords.

Same dormant-by-default pattern as sms_client.py: if GEMINI_API_KEY isn't
set, or the call fails/times out/returns something unparseable for any
reason, this returns None and the caller falls back to the existing
OTHER/MODERATE default — a Gemini outage, bad key, or free-tier quota
exhaustion must never break report submission, which is the app's actual
core function.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from somfound.config import GEMINI_API_KEY, GEMINI_MODEL
from somfound.models import Category, Urgency

logger = logging.getLogger("somfound.llm_classifier")

# Wall-clock budget for the whole call, enforced by us rather than trusted to
# the SDK's own timeout handling — the SDK's http_options timeout has
# documented reliability issues (google-genai#911, #1330) and also has a
# server-side *minimum* of 10s, too slow for a fallback in a request path.
# Abandoning the future at this point doesn't kill the background thread
# (Python can't forcibly cancel one), it just stops waiting on it — the
# ThreadPoolExecutor is shut down with wait=False so *we* don't block on it
# either.
LLM_TIMEOUT_SECONDS = 6

_CATEGORY_HINTS = {
    Category.CRIME_SAFETY: "crime, violence, theft, or a safety threat to people",
    Category.INFRASTRUCTURE: "broken or damaged roads, bridges, power, or other public infrastructure",
    Category.NEEDS_RESOURCES: "a community need such as water, food, or medical help",
    Category.COMMUNITY_DEV: "positive local news — a new school, market, or development",
    Category.OTHER: "anything that doesn't clearly fit the categories above",
}
_URGENCY_HINTS = {
    Urgency.CRITICAL: "immediate danger to someone's life or safety, needs help right now",
    Urgency.HIGH: "a serious problem needing attention soon, not an active emergency",
    Urgency.MODERATE: "a real problem, but not urgent",
    Urgency.INFORMATIONAL: "just news or information — nothing broken, dangerous, or missing",
}

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "urgency": {"type": "string", "enum": [u.value for u in Urgency]},
    },
    "required": ["category", "urgency"],
}


def _build_prompt(description: str) -> str:
    categories = "\n".join(f"- {c.value}: {hint}" for c, hint in _CATEGORY_HINTS.items())
    urgencies = "\n".join(f"- {u.value}: {hint}" for u, hint in _URGENCY_HINTS.items())
    return (
        "You are triaging a community report for a Nigerian community-safety and "
        "development app. Read the report and pick the single best category and "
        f"urgency level.\n\nCategories:\n{categories}\n\nUrgency levels:\n{urgencies}\n\n"
        f'Report: "{description}"'
    )


def _call_gemini(description: str) -> str:
    """The actual network call — split out so tests can monkeypatch just
    this function instead of needing a real API key or network access.
    Raises on any failure; the caller (guess_category_urgency_with_llm)
    handles it."""
    # Imported lazily so a missing/broken install of google-genai only ever
    # matters if this code path is actually reached (i.e. a key is set).
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_build_prompt(description),
        config={
            "response_mime_type": "application/json",
            "response_json_schema": _RESPONSE_SCHEMA,
            "temperature": 0,
            "max_output_tokens": 200,
            "thinking_config": {"thinking_budget": 0},  # simple classification, no need to reason
        },
    )
    return response.text


def guess_category_urgency_with_llm(description: str) -> tuple[Category, Urgency] | None:
    """None means "couldn't classify" for any reason (disabled, network
    error, timeout, bad response) — always safe for the caller to treat the
    same as "no LLM available" and fall back to the keyword default."""
    if not GEMINI_API_KEY:
        return None

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_call_gemini, description)
        raw = future.result(timeout=LLM_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning("Gemini classification timed out after %ss", LLM_TIMEOUT_SECONDS)
        return None
    except Exception:
        logger.exception("Gemini classification failed")
        return None
    finally:
        executor.shutdown(wait=False)

    try:
        data = json.loads(raw)
        category = Category(data["category"])
        urgency = Urgency(data["urgency"])
    except Exception:
        logger.exception("Gemini returned something unparseable: %r", raw)
        return None

    return category, urgency

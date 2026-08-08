"""Optional LLM fallback for category/urgency classification on the web
report form — only used when sms_parser.guess_category_urgency() can't find
any keyword match at all (see routers/pages.py::submit_report). Keyword
matching stays the primary, fast, free path for the common case; this only
kicks in for the natural-language descriptions that don't hit any of the
~12 known keywords.

Two providers, tried in order — Gemini first, then Mistral only if Gemini
itself couldn't classify (unset, error, timeout, bad response). This is a
resilience fallback against one provider's outage/quota, not a second
opinion run in parallel: Mistral never runs if Gemini already returned a
usable answer.

Same dormant-by-default pattern as sms_client.py at every stage: if neither
API key is set, or every attempted call fails/times out/returns something
unparseable, this returns None and the caller falls back to the existing
OTHER/MODERATE default. A provider outage, bad key, or free-tier quota
exhaustion must never break report submission, which is the app's actual
core function.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from somfound.config import GEMINI_API_KEY, GEMINI_MODEL, MISTRAL_API_KEY, MISTRAL_MODEL
from somfound.models import Category, Urgency

logger = logging.getLogger("somfound.llm_classifier")

# Wall-clock budget per provider, enforced by us rather than trusted to each
# SDK's own timeout handling — Gemini's http_options timeout has documented
# reliability issues (google-genai#911, #1330) and also has a server-side
# *minimum* of 10s, too slow for a fallback in a request path. Abandoning the
# future at this point doesn't kill the background thread (Python can't
# forcibly cancel one), it just stops waiting on it — the ThreadPoolExecutor
# is shut down with wait=False so *we* don't block on it either.
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
    Raises on any failure; the caller (_classify_with) handles it."""
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


def _call_mistral(description: str) -> str:
    """Same contract as _call_gemini — split out for the same reason."""
    from mistralai.client import Mistral
    from mistralai.client.models.jsonschema import JSONSchema
    from mistralai.client.models.responseformat import ResponseFormat

    client = Mistral(api_key=MISTRAL_API_KEY)
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[{"role": "user", "content": _build_prompt(description)}],
        response_format=ResponseFormat(
            type="json_schema",
            json_schema=JSONSchema(name="classification", schema=_RESPONSE_SCHEMA, strict=True),
        ),
        temperature=0,
        max_tokens=200,
        timeout_ms=LLM_TIMEOUT_SECONDS * 1000,
    )
    return response.choices[0].message.content


def _run_with_timeout(call, description: str, provider_name: str) -> str | None:
    """Runs `call(description)` with our own hard wall-clock timeout (see
    LLM_TIMEOUT_SECONDS' docstring above for why we don't trust either SDK's
    own timeout handling for this). Returns None on any failure — timeout,
    network error, API error, anything."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(call, description)
        return future.result(timeout=LLM_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning("%s classification timed out after %ss", provider_name, LLM_TIMEOUT_SECONDS)
        return None
    except Exception:
        logger.exception("%s classification failed", provider_name)
        return None
    finally:
        executor.shutdown(wait=False)


def _parse(raw: str, provider_name: str) -> tuple[Category, Urgency] | None:
    """Defense in depth — the response_json_schema on both providers should
    already constrain this, but never trust that blindly."""
    try:
        data = json.loads(raw)
        return Category(data["category"]), Urgency(data["urgency"])
    except Exception:
        logger.exception("%s returned something unparseable: %r", provider_name, raw)
        return None


def _friendly_model_name(model_id: str) -> str:
    """'gemini-3.5-flash' -> 'Gemini 3.5 Flash', 'mistral-small-latest' ->
    'Mistral Small' — for the report form's user-facing note about which AI
    can help categorize a report. No hardcoded name-to-name mapping to keep
    up to date: this degrades gracefully (still readable, just less pretty)
    if GEMINI_MODEL/MISTRAL_MODEL ever point at a model name shaped
    differently than today's."""
    parts = model_id.split("-")
    if parts and parts[-1].lower() == "latest":
        parts = parts[:-1]
    return " ".join(p if any(ch.isdigit() for ch in p) else p.capitalize() for p in parts)


def describe_configured_providers() -> str:
    """A short, honest, user-facing note for the report form about which AI
    model(s) can help categorize a report — empty string if neither
    provider is configured, so "dormant" means truly invisible, not just
    unused. Mirrors the real fallback order (Gemini first, Mistral only as
    backup), not two providers working in parallel."""
    names = []
    if GEMINI_API_KEY:
        names.append(_friendly_model_name(GEMINI_MODEL))
    if MISTRAL_API_KEY:
        names.append(_friendly_model_name(MISTRAL_MODEL))

    if not names:
        return ""
    if len(names) == 1:
        return f"Category/urgency can get AI help from {names[0]} when no keyword matches."
    return f"Category/urgency can get AI help from {names[0]} (backed up by {names[1]}) when no keyword matches."


def guess_category_urgency_with_llm(description: str) -> tuple[Category, Urgency] | None:
    """None means "couldn't classify" for any reason — always safe for the
    caller to fall back to the keyword default. Tries Gemini first, then
    Mistral only if Gemini itself didn't produce a usable answer (not
    configured, or failed) — a resilience fallback against one provider's
    outage/quota, never a second opinion on an answer Gemini already gave."""
    if GEMINI_API_KEY:
        raw = _run_with_timeout(_call_gemini, description, "Gemini")
        if raw is not None:
            result = _parse(raw, "Gemini")
            if result is not None:
                return result

    if MISTRAL_API_KEY:
        raw = _run_with_timeout(_call_mistral, description, "Mistral")
        if raw is not None:
            result = _parse(raw, "Mistral")
            if result is not None:
                return result

    return None

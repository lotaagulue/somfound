"""Optional LLM help for the web report form and public map — two separate
things built on the same shared provider infrastructure:

1. Category/urgency classification (guess_category_urgency_with_llm) — only
   used when sms_parser.guess_category_urgency() can't find any keyword
   match at all (see routers/pages.py::submit_report). Keyword matching
   stays the primary, fast, free path for the common case; this only kicks
   in for natural-language descriptions that don't hit any of the ~12 known
   keywords.
2. Map-popup summarization (summarize_description) — a short AI summary of
   a long description, generated once at moderator-approval time (see
   routers/moderation.py) and cached on Report.summary from then on, never
   regenerated on every map load.

Two providers, tried in order for either task — Gemini first, then Mistral
only if Gemini itself couldn't produce a usable answer (unset, error,
timeout, bad response). This is a resilience fallback against one
provider's outage/quota, not a second opinion run in parallel: Mistral
never runs if Gemini already returned something usable.

Same dormant-by-default pattern as sms_client.py at every stage: if neither
API key is set, or every attempted call fails/times out/returns something
unparseable, both entry points return None and the caller falls back to
its existing non-AI default (the OTHER/MODERATE guess, or just the full
description on the map). A provider outage, bad key, or free-tier quota
exhaustion must never break report submission or hide a report's content —
this is a convenience layer, never the only copy of what was reported.
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

# Below this length, a description is already short enough that an AI
# "summary" wouldn't shorten anything meaningful — skip the call entirely
# rather than spend a request on a summary that's barely different from,
# or even longer than, the original.
SUMMARY_SKIP_BELOW_CHARS = 100

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

_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "urgency": {"type": "string", "enum": [u.value for u in Urgency]},
    },
    "required": ["category", "urgency"],
}


def _build_classification_prompt(description: str) -> str:
    categories = "\n".join(f"- {c.value}: {hint}" for c, hint in _CATEGORY_HINTS.items())
    urgencies = "\n".join(f"- {u.value}: {hint}" for u, hint in _URGENCY_HINTS.items())
    return (
        "You are triaging a community report for a Nigerian community-safety and "
        "development app. Read the report and pick the single best category and "
        f"urgency level.\n\nCategories:\n{categories}\n\nUrgency levels:\n{urgencies}\n\n"
        f'Report: "{description}"'
    )


def _build_summary_prompt(description: str) -> str:
    return (
        "Summarize the following community report in one short, plain sentence "
        "(20 words or fewer) that someone skimming a map could read at a glance. "
        "Keep the key facts — what happened, roughly where, how urgent it sounds — "
        "and drop everything else. Do not add any information, speculation, or "
        "commentary that isn't in the original report.\n\n"
        f'Report: "{description}"'
    )


def _call_gemini(prompt: str, *, json_schema: dict | None = None, max_output_tokens: int = 200) -> str:
    """The actual network call — split out so tests can monkeypatch just
    this function instead of needing a real API key or network access.
    Raises on any failure; the caller (_run_with_timeout) handles it.
    json_schema=None means plain-text output (summarization); a schema
    switches on structured JSON output (classification)."""
    # Imported lazily so a missing/broken install of google-genai only ever
    # matters if this code path is actually reached (i.e. a key is set).
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = {
        "temperature": 0,
        "max_output_tokens": max_output_tokens,
        "thinking_config": {"thinking_budget": 0},  # simple tasks, no need to reason
    }
    if json_schema is not None:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = json_schema
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
    return response.text


def _call_mistral(prompt: str, *, json_schema: dict | None = None, max_output_tokens: int = 200) -> str:
    """Same contract as _call_gemini — split out for the same reason."""
    from mistralai.client import Mistral

    client = Mistral(api_key=MISTRAL_API_KEY)
    kwargs = {}
    if json_schema is not None:
        from mistralai.client.models.jsonschema import JSONSchema
        from mistralai.client.models.responseformat import ResponseFormat

        kwargs["response_format"] = ResponseFormat(
            type="json_schema",
            json_schema=JSONSchema(name="classification", schema=json_schema, strict=True),
        )
    response = client.chat.complete(
        model=MISTRAL_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_output_tokens,
        timeout_ms=LLM_TIMEOUT_SECONDS * 1000,
        **kwargs,
    )
    return response.choices[0].message.content


def _run_with_timeout(call, prompt: str, provider_name: str, **call_kwargs) -> str | None:
    """Runs `call(prompt, **call_kwargs)` with our own hard wall-clock
    timeout (see LLM_TIMEOUT_SECONDS' docstring above for why we don't trust
    either SDK's own timeout handling for this). Returns None on any
    failure — timeout, network error, API error, anything."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(call, prompt, **call_kwargs)
        return future.result(timeout=LLM_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning("%s call timed out after %ss", provider_name, LLM_TIMEOUT_SECONDS)
        return None
    except Exception:
        logger.exception("%s call failed", provider_name)
        return None
    finally:
        executor.shutdown(wait=False)


def _parse_classification(raw: str, provider_name: str) -> tuple[Category, Urgency] | None:
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
    unused. Names appear in the same order as the real fallback
    (Gemini first, Mistral only as backup) even though the copy itself is
    deliberately simple rather than spelling that mechanism out."""
    names = []
    if GEMINI_API_KEY:
        names.append(_friendly_model_name(GEMINI_MODEL))
    if MISTRAL_API_KEY:
        names.append(_friendly_model_name(MISTRAL_MODEL))

    if not names:
        return ""
    return f"With help from {' and '.join(names)}"


def guess_category_urgency_with_llm(description: str) -> tuple[Category, Urgency] | None:
    """None means "couldn't classify" for any reason — always safe for the
    caller to fall back to the keyword default. Tries Gemini first, then
    Mistral only if Gemini itself didn't produce a usable answer (not
    configured, or failed) — a resilience fallback against one provider's
    outage/quota, never a second opinion on an answer Gemini already gave."""
    prompt = _build_classification_prompt(description)

    if GEMINI_API_KEY:
        raw = _run_with_timeout(_call_gemini, prompt, "Gemini", json_schema=_CLASSIFICATION_SCHEMA)
        if raw is not None:
            result = _parse_classification(raw, "Gemini")
            if result is not None:
                return result

    if MISTRAL_API_KEY:
        raw = _run_with_timeout(_call_mistral, prompt, "Mistral", json_schema=_CLASSIFICATION_SCHEMA)
        if raw is not None:
            result = _parse_classification(raw, "Mistral")
            if result is not None:
                return result

    return None


def summarize_description(description: str) -> str | None:
    """One-shot AI summary of a report's full description, meant to be
    called once at moderator-approval time and cached on Report.summary
    from then on (see routers/moderation.py) — never regenerated on every
    map load. None means "no summary" for any reason: the description is
    already short enough that summarizing wouldn't help
    (SUMMARY_SKIP_BELOW_CHARS), neither provider is configured, or every
    attempted call failed. The map always still has the full original
    description to fall back to — this is a convenience layer, never the
    only copy of what was actually reported."""
    if len(description) < SUMMARY_SKIP_BELOW_CHARS:
        return None

    prompt = _build_summary_prompt(description)

    if GEMINI_API_KEY:
        summary = _run_with_timeout(_call_gemini, prompt, "Gemini", max_output_tokens=60)
        # A whitespace-only response isn't a usable summary — fall through
        # to Mistral rather than treating empty-after-strip as success.
        if summary and summary.strip():
            return summary.strip()

    if MISTRAL_API_KEY:
        summary = _run_with_timeout(_call_mistral, prompt, "Mistral", max_output_tokens=60)
        if summary and summary.strip():
            return summary.strip()

    return None

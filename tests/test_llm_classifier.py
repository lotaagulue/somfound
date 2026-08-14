"""Unit tests for the Gemini -> Mistral LLM fallback chain (classification
and summarization both) — all network calls are mocked out via
monkeypatching llm_classifier._call_gemini / _call_mistral, so these run
with no API keys, no network access, and no cost, same as the rest of the
suite.

Every test sets both GEMINI_API_KEY and MISTRAL_API_KEY explicitly (rather
than relying on them being absent from the environment) so behavior is
deterministic regardless of what's actually in a developer's local .env —
this module reads them once at import time into its own names, so it's
those names that need patching, not os.environ.

_call_gemini/_call_mistral now take (prompt, *, json_schema=None,
max_output_tokens=200) — mocks below accept **kwargs so they don't break
when a caller passes those through."""

import pytest

from somfound import llm_classifier
from somfound.models import Category, Urgency


@pytest.fixture(autouse=True)
def _no_keys_by_default(monkeypatch):
    """Every test starts with both providers disabled and opts in
    explicitly — avoids a test silently passing because it forgot to
    disable a provider it didn't mean to exercise."""
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "")


def _never_called(name):
    def _fn(prompt, **kwargs):
        raise AssertionError(f"{name} should not have been called")

    return _fn


# --- guess_category_urgency_with_llm ---


def test_returns_none_and_calls_nothing_when_neither_key_is_set(monkeypatch):
    monkeypatch.setattr(llm_classifier, "_call_gemini", _never_called("Gemini"))
    monkeypatch.setattr(llm_classifier, "_call_mistral", _never_called("Mistral"))

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_gemini_result_used_and_mistral_never_called_when_gemini_succeeds(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")
    monkeypatch.setattr(
        llm_classifier,
        "_call_gemini",
        lambda prompt, **kwargs: '{"category": "crime_safety", "urgency": "critical"}',
    )
    monkeypatch.setattr(llm_classifier, "_call_mistral", _never_called("Mistral"))

    result = llm_classifier.guess_category_urgency_with_llm("something scary happened")
    assert result == (Category.CRIME_SAFETY, Urgency.CRITICAL)


def test_falls_through_to_mistral_when_gemini_fails(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")

    def _gemini_boom(prompt, **kwargs):
        raise RuntimeError("simulated Gemini outage")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _gemini_boom)
    monkeypatch.setattr(
        llm_classifier, "_call_mistral", lambda prompt, **kwargs: '{"category": "infrastructure", "urgency": "high"}'
    )

    result = llm_classifier.guess_category_urgency_with_llm("a bridge is down")
    assert result == (Category.INFRASTRUCTURE, Urgency.HIGH)


def test_mistral_called_directly_when_only_mistral_is_configured(monkeypatch):
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", _never_called("Gemini"))
    monkeypatch.setattr(
        llm_classifier, "_call_mistral", lambda prompt, **kwargs: '{"category": "other", "urgency": "informational"}'
    )

    result = llm_classifier.guess_category_urgency_with_llm("just saying hi")
    assert result == (Category.OTHER, Urgency.INFORMATIONAL)


def test_returns_none_when_both_providers_fail(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")

    def _boom(prompt, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _boom)
    monkeypatch.setattr(llm_classifier, "_call_mistral", _boom)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_timeout(monkeypatch):
    import time

    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    # Keep the test fast: shrink the timeout instead of actually waiting
    # LLM_TIMEOUT_SECONDS (6s) for a slow fake call.
    monkeypatch.setattr(llm_classifier, "LLM_TIMEOUT_SECONDS", 0.05)

    def _slow(prompt, **kwargs):
        time.sleep(0.5)
        return '{"category": "other", "urgency": "moderate"}'

    monkeypatch.setattr(llm_classifier, "_call_gemini", _slow)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda prompt, **kwargs: "not json at all")

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_invalid_enum_value(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    bad_json = '{"category": "not_a_real_category", "urgency": "critical"}'
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda prompt, **kwargs: bad_json)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_classification_prompt_mentions_the_report_text():
    prompt = llm_classifier._build_classification_prompt("a very specific marker phrase")
    assert "a very specific marker phrase" in prompt


# --- summarize_description (the map popup's short summary) ---

_LONG_DESCRIPTION = "x" * (llm_classifier.SUMMARY_SKIP_BELOW_CHARS + 1)
_SHORT_DESCRIPTION = "x" * (llm_classifier.SUMMARY_SKIP_BELOW_CHARS - 1)


def test_summarize_skips_short_descriptions_without_calling_anything(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", _never_called("Gemini"))

    assert llm_classifier.summarize_description(_SHORT_DESCRIPTION) is None


def test_summarize_returns_none_when_neither_key_configured(monkeypatch):
    monkeypatch.setattr(llm_classifier, "_call_gemini", _never_called("Gemini"))
    monkeypatch.setattr(llm_classifier, "_call_mistral", _never_called("Mistral"))

    assert llm_classifier.summarize_description(_LONG_DESCRIPTION) is None


def test_summarize_returns_gemini_result_and_strips_whitespace(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda prompt, **kwargs: "  A short summary.  \n")
    monkeypatch.setattr(llm_classifier, "_call_mistral", _never_called("Mistral"))

    assert llm_classifier.summarize_description(_LONG_DESCRIPTION) == "A short summary."


def test_summarize_falls_through_to_mistral_when_gemini_fails(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")

    def _gemini_boom(prompt, **kwargs):
        raise RuntimeError("simulated Gemini outage")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _gemini_boom)
    monkeypatch.setattr(llm_classifier, "_call_mistral", lambda prompt, **kwargs: "Backup summary.")

    assert llm_classifier.summarize_description(_LONG_DESCRIPTION) == "Backup summary."


def test_summarize_returns_none_when_both_providers_fail(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")

    def _boom(prompt, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _boom)
    monkeypatch.setattr(llm_classifier, "_call_mistral", _boom)

    assert llm_classifier.summarize_description(_LONG_DESCRIPTION) is None


def test_summarize_treats_empty_response_as_no_summary(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda prompt, **kwargs: "   ")

    assert llm_classifier.summarize_description(_LONG_DESCRIPTION) is None


def test_summary_prompt_mentions_the_report_text():
    prompt = llm_classifier._build_summary_prompt("a very specific marker phrase")
    assert "a very specific marker phrase" in prompt


def test_classification_call_uses_json_schema_summarize_does_not(monkeypatch):
    """Not a behavioral test of the providers themselves (those are
    mocked everywhere else) — just confirms guess_category_urgency_with_llm
    and summarize_description ask _call_gemini for structured vs. plain
    output respectively, since that's the one thing distinguishing the two
    call sites now that they share _call_gemini/_call_mistral."""
    seen = {}

    def _fake_call(prompt, **kwargs):
        seen.update(kwargs)
        return '{"category": "other", "urgency": "moderate"}'

    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_classifier, "_call_gemini", _fake_call)
    llm_classifier.guess_category_urgency_with_llm("anything")
    assert seen.get("json_schema") == llm_classifier._CLASSIFICATION_SCHEMA

    seen.clear()

    def _fake_summary_call(prompt, **kwargs):
        seen.update(kwargs)
        return "a summary"

    monkeypatch.setattr(llm_classifier, "_call_gemini", _fake_summary_call)
    llm_classifier.summarize_description(_LONG_DESCRIPTION)
    assert "json_schema" not in seen


# --- describe_configured_providers (the report form's "we use AI" note) ---


def test_friendly_model_name_formats_version_and_strips_latest():
    assert llm_classifier._friendly_model_name("gemini-3.5-flash") == "Gemini 3.5 Flash"
    assert llm_classifier._friendly_model_name("mistral-small-latest") == "Mistral Small"


def test_describe_configured_providers_empty_when_neither_configured():
    assert llm_classifier.describe_configured_providers() == ""


def test_describe_configured_providers_mentions_gemini_only(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_classifier, "GEMINI_MODEL", "gemini-3.5-flash")

    assert llm_classifier.describe_configured_providers() == "With help from Gemini 3.5 Flash"


def test_describe_configured_providers_mentions_both_in_fallback_order(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(llm_classifier, "GEMINI_MODEL", "gemini-3.5-flash")
    monkeypatch.setattr(llm_classifier, "MISTRAL_API_KEY", "fake-mistral-key")
    monkeypatch.setattr(llm_classifier, "MISTRAL_MODEL", "mistral-small-latest")

    note = llm_classifier.describe_configured_providers()
    assert note == "With help from Gemini 3.5 Flash and Mistral Small"

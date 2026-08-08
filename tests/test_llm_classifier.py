"""Unit tests for the Gemini LLM fallback — all network calls are mocked out
via monkeypatching llm_classifier._call_gemini, so these run with no API key,
no network access, and no cost, same as the rest of the suite."""

import pytest

from somfound import llm_classifier
from somfound.models import Category, Urgency


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """Most tests here want the "enabled" path — set a fake key by default,
    the one test that cares about the disabled path overrides it back to ''."""
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "fake-key-for-tests")


def test_returns_none_and_never_calls_gemini_when_no_api_key(monkeypatch):
    monkeypatch.setattr(llm_classifier, "GEMINI_API_KEY", "")

    def _should_not_be_called(description):
        raise AssertionError("_call_gemini should not be invoked without an API key")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _should_not_be_called)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_parsed_category_and_urgency_on_success(monkeypatch):
    monkeypatch.setattr(
        llm_classifier, "_call_gemini", lambda description: '{"category": "crime_safety", "urgency": "critical"}'
    )

    result = llm_classifier.guess_category_urgency_with_llm("something scary happened")
    assert result == (Category.CRIME_SAFETY, Urgency.CRITICAL)


def test_returns_none_when_the_call_raises(monkeypatch):
    def _boom(description):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(llm_classifier, "_call_gemini", _boom)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_timeout(monkeypatch):
    import time

    # Keep the test fast: shrink the timeout instead of actually waiting
    # LLM_TIMEOUT_SECONDS (6s) for a slow fake call.
    monkeypatch.setattr(llm_classifier, "LLM_TIMEOUT_SECONDS", 0.05)

    def _slow(description):
        time.sleep(0.5)
        return '{"category": "other", "urgency": "moderate"}'

    monkeypatch.setattr(llm_classifier, "_call_gemini", _slow)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda description: "not json at all")

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_returns_none_on_invalid_enum_value(monkeypatch):
    # Defense in depth — the response_json_schema should already constrain
    # this, but never trust that blindly.
    bad_json = '{"category": "not_a_real_category", "urgency": "critical"}'
    monkeypatch.setattr(llm_classifier, "_call_gemini", lambda description: bad_json)

    assert llm_classifier.guess_category_urgency_with_llm("anything") is None


def test_prompt_mentions_the_report_text():
    prompt = llm_classifier._build_prompt("a very specific marker phrase")
    assert "a very specific marker phrase" in prompt

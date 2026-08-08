from somfound import crud
from somfound.models import Category, Urgency
from somfound.routers import pages


def test_moderation_queue_requires_auth(client):
    response = client.get("/moderate")
    assert response.status_code == 401


def test_web_report_is_pending_until_approved(client, moderator_auth):
    submit = client.post(
        "/report",
        data={
            "category": "infrastructure",
            "urgency": "moderate",
            "description": "Pothole test report for the automated test suite",
            "lat": "6.15",
            "lon": "6.83",
        },
    )
    # Rendered directly (not a redirect) so a freshly generated wallet code
    # never travels through a URL — see routers/pages.py.
    assert submit.status_code == 200
    assert "reward wallet code" in submit.text

    public = client.get("/api/reports").json()
    assert not any("automated test suite" in r["description"] for r in public)

    queue = client.get("/moderate", auth=moderator_auth)
    assert queue.status_code == 200
    assert "automated test suite" in queue.text

    # Queue is ordered oldest-first, so our just-submitted report is the last
    # pending entry — pull its id from the last approve-form action in the HTML.
    import re

    matches = re.findall(r'/moderate/(\d+)/approve', queue.text)
    assert matches, "expected an approve form in the pending queue"
    report_id = matches[-1]

    approve = client.post(
        f"/moderate/{report_id}/approve", data={"notes": ""}, auth=moderator_auth, follow_redirects=False
    )
    assert approve.status_code == 303

    public_after = client.get("/api/reports").json()
    assert any("automated test suite" in r["description"] for r in public_after)


def test_resolved_report_disappears_from_default_map_but_available_via_toggle(client, moderator_auth):
    import re

    submit = client.post(
        "/report",
        data={
            "category": "infrastructure",
            "urgency": "critical",
            "description": "resolved-visibility-marker",
            "lat": "6.15",
            "lon": "6.83",
        },
    )
    assert submit.status_code == 200

    queue = client.get("/moderate", auth=moderator_auth)
    report_id = re.findall(r"/moderate/(\d+)/approve", queue.text)[-1]
    client.post(f"/moderate/{report_id}/approve", data={"notes": ""}, auth=moderator_auth)

    published = client.get("/api/reports").json()
    assert any(r["description"] == "resolved-visibility-marker" for r in published)

    client.post(f"/moderate/{report_id}/resolve", auth=moderator_auth)

    # Default view: resolved reports don't keep looking live.
    default_view = client.get("/api/reports").json()
    assert not any(r["description"] == "resolved-visibility-marker" for r in default_view)

    # Explicit opt-in: still available, but greyed out rather than urgency-colored.
    with_resolved = client.get("/api/reports?include_resolved=true").json()
    match = next(r for r in with_resolved if r["description"] == "resolved-visibility-marker")
    assert match["status"] == "resolved"
    assert match["color"] == "#9ca3af"  # RESOLVED_COLOR, not critical's red


def test_sms_inbound_creates_categorized_pending_report(client, moderator_auth):
    response = client.post(
        "/sms/inbound", data={"from": "+2348000000001", "text": "WATER Nsukka borehole broken pytest marker"}
    )
    assert response.status_code == 200
    assert response.json()["report_id"] is not None

    queue = client.get("/moderate", auth=moderator_auth)
    assert "pytest marker" in queue.text
    assert "Needs &amp; Resources" in queue.text or "Needs & Resources" in queue.text


def test_sms_rate_limit_stops_after_threshold(client):
    for i in range(crud.MAX_PENDING_PER_REPORTER):
        client.post("/sms/inbound", data={"from": "+2348000000002", "text": f"HELP spam attempt {i}"})

    # One past the threshold should be rate-limited: no new report created.
    blocked = client.post("/sms/inbound", data={"from": "+2348000000002", "text": "HELP spam attempt blocked"})
    assert blocked.json()["report_id"] is None


def _report_payload(description: str, **overrides) -> dict:
    data = {
        "category": "infrastructure",
        "urgency": "moderate",
        "description": description,
        "lat": "6.15",
        "lon": "6.83",
    }
    data.update(overrides)
    return data


def _approve_and_get_id(client, moderator_auth) -> str:
    """Grab the most-recently-submitted pending report's id (queue is
    oldest-first) without approving it yet — the caller decides when."""
    import re

    queue = client.get("/moderate", auth=moderator_auth)
    return re.findall(r"/moderate/(\d+)/approve", queue.text)[-1]


def _approve(client, moderator_auth, report_id: str) -> None:
    client.post(f"/moderate/{report_id}/approve", data={"notes": ""}, auth=moderator_auth)


def test_web_report_rate_limit_stops_anonymous_spam(client, moderator_auth):
    # No phone given on any of these — all share the same fallback rate-limit
    # key (a hash of the test client's IP), same as one anonymous spammer.
    # Left pending (not approved) until the end of the test — the whole
    # point is proving MAX_PENDING_PER_REPORTER *simultaneously* pending
    # reports block the next one.
    created_ids = []
    for i in range(crud.MAX_PENDING_PER_REPORTER):
        r = client.post("/report", data=_report_payload(f"anon spam marker {i}"))
        assert "reward wallet code" in r.text  # each of these succeeds
        created_ids.append(_approve_and_get_id(client, moderator_auth))

    fourth = client.post("/report", data=_report_payload("anon spam marker blocked"))
    assert fourth.status_code == 200
    assert "still waiting for review" in fourth.text
    assert "anon spam marker blocked" not in fourth.text  # not actually created

    public = client.get("/api/reports").json()
    assert not any("anon spam marker blocked" in r["description"] for r in public)

    # Clean up: this test DB is shared across the whole suite (see
    # conftest.py), so leaving these pending would permanently exhaust the
    # anonymous-IP bucket for every later test that submits a no-phone
    # report — approve them now that the assertions above are done.
    for report_id in created_ids:
        _approve(client, moderator_auth, report_id)


def test_web_report_rate_limit_is_independent_per_phone(client, moderator_auth):
    # Exhaust the anonymous (no-phone) bucket first — again left pending
    # until cleanup at the end, for the same reason as above.
    created_ids = []
    for i in range(crud.MAX_PENDING_PER_REPORTER):
        r = client.post("/report", data=_report_payload(f"anon bucket filler {i}"))
        assert "reward wallet code" in r.text
        created_ids.append(_approve_and_get_id(client, moderator_auth))

    blocked = client.post("/report", data=_report_payload("anon bucket filler blocked"))
    assert "still waiting for review" in blocked.text

    # A submission WITH a phone number uses a different rate-limit key (the
    # phone's hash, not the IP's) and should go through even though the
    # anonymous bucket above is full.
    with_phone = client.post(
        "/report", data=_report_payload("phone-keyed marker", phone="+2348055556666")
    )
    assert "reward wallet code" in with_phone.text
    phone_report_id = _approve_and_get_id(client, moderator_auth)

    queue = client.get("/moderate", auth=moderator_auth)
    assert "phone-keyed marker" in queue.text

    for report_id in [*created_ids, phone_report_id]:
        _approve(client, moderator_auth, report_id)


def test_web_report_description_too_long_is_rejected(client):
    too_long = "x" * 2001
    response = client.post("/report", data=_report_payload(too_long))
    assert response.status_code == 200
    assert "too long" in response.text

    public = client.get("/api/reports").json()
    assert not any(r["description"] == too_long for r in public)


def test_web_report_auto_categorizes_when_left_blank(client, moderator_auth):
    # Distinct phone so this doesn't touch the shared anonymous-IP
    # rate-limit bucket used by other tests in this file.
    response = client.post(
        "/report",
        data=_report_payload(
            "There was an armed robbery last night, please send crime officers auto-guess-marker",
            category="",
            urgency="",
            phone="+2348033334444",
        ),
    )
    assert response.status_code == 200
    assert "We categorized this as" in response.text
    assert "Crime &amp; Safety" in response.text or "Crime & Safety" in response.text
    assert "Critical" in response.text  # HIGH from CRIME, escalated by "armed"

    queue = client.get("/moderate", auth=moderator_auth)
    assert "auto-guess-marker" in queue.text
    assert "Crime &amp; Safety" in queue.text or "Crime & Safety" in queue.text

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


def test_web_report_explicit_category_and_urgency_override_the_guess(client, moderator_auth):
    response = client.post(
        "/report",
        data=_report_payload(
            "There was an armed robbery — explicit-override-marker",
            category="community_dev",
            urgency="informational",
            phone="+2348044445555",
        ),
    )
    assert response.status_code == 200
    assert "We categorized this as" not in response.text  # both fields were explicit, nothing auto-detected

    queue = client.get("/moderate", auth=moderator_auth)
    assert "explicit-override-marker" in queue.text
    assert "Community &amp; Development" in queue.text or "Community & Development" in queue.text

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


# --- Resubmission (browser "back" past a no-store page, double-tap, etc.) ---


def test_resubmitting_the_same_token_replays_the_original_wallet_code(client, moderator_auth):
    # No phone — this is exactly the reported bug: hitting "back" to a
    # no-store confirmation page and having the browser resend the POST used
    # to mint a *second*, orphaned anonymous wallet with a different code.
    payload = _report_payload("resubmit-replay-marker", category="", urgency="", submission_token="tok-replay-1")

    first = client.post("/report", data=payload)
    assert first.status_code == 200
    first_code = first.text.split("reward wallet code: <strong>")[1].split("</strong>")[0]

    second = client.post("/report", data=payload)  # exact same body, same token
    assert second.status_code == 200
    second_code = second.text.split("reward wallet code: <strong>")[1].split("</strong>")[0]

    assert second_code == first_code, "resubmission minted a new wallet instead of replaying the original"

    # Only one report actually got created, not two.
    queue = client.get("/moderate", auth=moderator_auth)
    assert queue.text.count("resubmit-replay-marker") == 1

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


def test_a_fresh_token_creates_an_independent_report(client, moderator_auth):
    first = client.post(
        "/report", data=_report_payload("fresh-token-marker-1", submission_token="tok-fresh-a")
    )
    second = client.post(
        "/report", data=_report_payload("fresh-token-marker-2", submission_token="tok-fresh-b")
    )
    first_code = first.text.split("reward wallet code: <strong>")[1].split("</strong>")[0]
    second_code = second.text.split("reward wallet code: <strong>")[1].split("</strong>")[0]
    assert first_code != second_code

    queue = client.get("/moderate", auth=moderator_auth)
    assert "fresh-token-marker-1" in queue.text
    assert "fresh-token-marker-2" in queue.text

    for _ in range(2):
        _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


def test_wallet_recovery_tip_shown_only_when_no_phone_was_given(client, moderator_auth):
    anonymous = client.post("/report", data=_report_payload("no-phone-tip-marker"))
    assert "Tip:" in anonymous.text and "no code to save" in anonymous.text

    with_phone = client.post(
        "/report", data=_report_payload("phone-given-no-tip-marker", phone="+2348011119999")
    )
    assert "Tip:" not in with_phone.text

    for _ in range(2):
        _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


# --- LLM fallback wiring (routers/pages.py) — see tests/test_llm_classifier.py
# for the classifier's own unit tests; these check it's actually *called* at
# the right time (and not called at the wrong time), with the network call
# itself mocked out so no real API key/network access is needed.


def test_llm_fallback_used_when_no_keyword_matches(client, moderator_auth, monkeypatch):
    monkeypatch.setattr(
        pages, "guess_category_urgency_with_llm", lambda description: (Category.CRIME_SAFETY, Urgency.CRITICAL)
    )

    response = client.post(
        "/report",
        data=_report_payload(
            "Something strange is going on that I cannot quite describe llm-fallback-marker",
            category="",
            urgency="",
        ),
    )
    assert response.status_code == 200
    assert "using AI" in response.text
    assert "Crime &amp; Safety" in response.text or "Crime & Safety" in response.text
    assert "Critical" in response.text

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


def test_llm_fallback_not_called_when_a_keyword_already_matches(client, moderator_auth, monkeypatch):
    def _should_not_be_called(description):
        raise AssertionError("LLM fallback should not run when a keyword already matched")

    monkeypatch.setattr(pages, "guess_category_urgency_with_llm", _should_not_be_called)

    response = client.post(
        "/report",
        data=_report_payload("CRIME reported near the junction llm-not-called-marker", category="", urgency=""),
    )
    assert response.status_code == 200
    assert "using AI" not in response.text

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


def test_llm_fallback_not_called_when_category_or_urgency_set_explicitly(client, moderator_auth, monkeypatch):
    def _should_not_be_called(description):
        raise AssertionError("LLM fallback should not run when the reporter set a field themselves")

    monkeypatch.setattr(pages, "guess_category_urgency_with_llm", _should_not_be_called)

    response = client.post(
        "/report",
        data=_report_payload(
            "Something strange is going on llm-explicit-override-marker",
            category="other",
            urgency="",
        ),
    )
    assert response.status_code == 200

    _approve(client, moderator_auth, _approve_and_get_id(client, moderator_auth))


# --- report form's "we use AI" note (pages.describe_configured_providers) ---


def test_report_form_shows_no_ai_note_by_default(client):
    # Default test env has neither GEMINI_API_KEY nor MISTRAL_API_KEY set.
    response = client.get("/report")
    assert "AI help" not in response.text


def test_report_form_shows_ai_note_when_a_provider_is_configured(client, monkeypatch):
    note = "Category/urgency can get AI help from Test Model when no keyword matches."
    monkeypatch.setattr(pages, "describe_configured_providers", lambda: note)
    response = client.get("/report")
    assert "Test Model" in response.text

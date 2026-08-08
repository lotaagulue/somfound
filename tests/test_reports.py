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
        follow_redirects=False,
    )
    assert submit.status_code == 303

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
    for i in range(4):
        client.post("/sms/inbound", data={"from": "+2348000000002", "text": f"HELP spam attempt {i}"})

    # The 4th (index 3) should have been rate-limited: no new report created.
    fourth = client.post("/sms/inbound", data={"from": "+2348000000002", "text": "HELP spam attempt 4"})
    assert fourth.json()["report_id"] is None

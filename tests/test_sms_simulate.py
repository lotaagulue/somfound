def test_simulate_form_renders(client):
    response = client.get("/sms/simulate")
    assert response.status_code == 200
    assert "Simulate an SMS report" in response.text


def test_simulate_submit_creates_pending_report_and_shows_parse_result(client, moderator_auth):
    response = client.post(
        "/sms/simulate",
        data={"phone": "+2348099999999", "text": "WATER Umuoji borehole broken simulate-marker"},
    )
    assert response.status_code == 200
    assert "Needs &amp; Resources" in response.text or "Needs & Resources" in response.text
    assert "Umuoji" in response.text

    queue = client.get("/moderate", auth=moderator_auth)
    assert "simulate-marker" in queue.text


def test_simulate_respects_rate_limit(client):
    for i in range(3):
        client.post("/sms/simulate", data={"phone": "+2348088888888", "text": f"HELP spam {i}"})

    limited = client.post("/sms/simulate", data={"phone": "+2348088888888", "text": "HELP spam 4"})
    assert "Rate-limited" in limited.text

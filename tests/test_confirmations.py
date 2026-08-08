import re


def _publish_a_report(client, moderator_auth, description="confirm-target"):
    client.post(
        "/report",
        data={
            "category": "infrastructure",
            "urgency": "moderate",
            "description": description,
            "lat": "6.15",
            "lon": "6.83",
        },
    )
    queue = client.get("/moderate", auth=moderator_auth)
    report_id = re.findall(r"/moderate/(\d+)/approve", queue.text)[-1]
    client.post(f"/moderate/{report_id}/approve", data={"notes": ""}, auth=moderator_auth)
    return int(report_id)


def test_confirming_increments_count(client, moderator_auth):
    report_id = _publish_a_report(client, moderator_auth)

    before = next(r for r in client.get("/api/reports").json() if r["id"] == report_id)
    assert before["confirmations_count"] == 0

    response = client.post(f"/api/reports/{report_id}/confirm")
    assert response.status_code == 200
    assert response.json() == {"confirmations_count": 1, "already_confirmed": False}

    after = next(r for r in client.get("/api/reports").json() if r["id"] == report_id)
    assert after["confirmations_count"] == 1


def test_same_session_confirming_twice_does_not_double_count(client, moderator_auth):
    report_id = _publish_a_report(client, moderator_auth)

    first = client.post(f"/api/reports/{report_id}/confirm").json()
    second = client.post(f"/api/reports/{report_id}/confirm").json()

    assert first == {"confirmations_count": 1, "already_confirmed": False}
    assert second == {"confirmations_count": 1, "already_confirmed": True}


def test_confirming_nonexistent_or_unpublished_report_404s(client):
    assert client.post("/api/reports/999999/confirm").status_code == 404

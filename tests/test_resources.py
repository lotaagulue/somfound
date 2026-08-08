def test_resources_admin_requires_auth(client):
    assert client.get("/resources").status_code == 401
    assert client.post("/resources", data={}).status_code == 401


def test_public_resources_list_starts_empty_and_needs_no_auth(client):
    response = client.get("/api/resources")
    assert response.status_code == 200
    assert response.json() == []


def test_moderator_can_add_and_update_a_kit_location(client, moderator_auth):
    create = client.post(
        "/resources",
        data={
            "resource_type": "first_aid_kit",
            "status": "installed",
            "lat": "6.2",
            "lon": "7.0",
            "notes": "community square meeting hall",
        },
        auth=moderator_auth,
        follow_redirects=False,
    )
    assert create.status_code == 303

    public = client.get("/api/resources").json()
    assert len(public) == 1
    resource = public[0]
    assert resource["resource_type"] == "first_aid_kit"
    assert resource["status"] == "installed"
    assert resource["color"] == "#0ca30c"  # installed = the "good" status color
    assert resource["notes"] == "community square meeting hall"

    admin_page = client.get("/resources", auth=moderator_auth)
    assert "community square meeting hall" in admin_page.text

    update = client.post(
        f"/resources/{resource['id']}/status",
        data={"status": "damaged", "notes": "reported broken lock"},
        auth=moderator_auth,
        follow_redirects=False,
    )
    assert update.status_code == 303

    updated = client.get("/api/resources").json()[0]
    assert updated["status"] == "damaged"
    assert updated["color"] == "#d03b3b"
    assert updated["notes"] == "reported broken lock"

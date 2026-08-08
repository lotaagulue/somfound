import re


def _submit_and_approve(client, moderator_auth, *, description, phone="", wallet_code="", award_points=0):
    data = {
        "category": "crime_safety",
        "urgency": "high",
        "description": description,
        "lat": "6.15",
        "lon": "6.83",
        "phone": phone,
        "wallet_code": wallet_code,
    }
    submit = client.post("/report", data=data)
    assert submit.status_code == 200

    match = re.search(r"reward wallet code: <strong>([A-Z0-9]+)</strong>", submit.text)
    assert match, "expected a wallet code in the confirmation banner"
    code = match.group(1)

    queue = client.get("/moderate", auth=moderator_auth)
    report_id = re.findall(r"/moderate/(\d+)/approve", queue.text)[-1]
    client.post(
        f"/moderate/{report_id}/approve",
        data={"notes": "", "award_points": str(award_points)},
        auth=moderator_auth,
    )
    return code


def test_anonymous_report_gets_a_new_wallet_shown_once(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="anon-wallet-marker")
    assert code

    lookup = client.post("/wallet", data={"identifier": code})
    assert lookup.status_code == 200
    assert f"Wallet {code}" in lookup.text


def _wallet_balance(response_text: str) -> int:
    match = re.search(r'font-weight:800;color:var\(--brand-dark\);margin:0 0 0.5rem;">(\d+)<', response_text)
    assert match, "expected a points balance in the wallet page"
    return int(match.group(1))


def test_moderator_awarded_points_land_in_the_wallet(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="points-marker", award_points=150)
    lookup = client.post("/wallet", data={"identifier": code})
    assert _wallet_balance(lookup.text) == 150


def test_same_phone_reuses_the_same_wallet_across_reports(client, moderator_auth):
    code1 = _submit_and_approve(
        client, moderator_auth, description="phone-wallet-1", phone="+2348022223333"
    )
    code2 = _submit_and_approve(
        client, moderator_auth, description="phone-wallet-2", phone="+2348022223333"
    )
    assert code1 == code2

    # Also findable by phone number directly, not just the code.
    by_phone = client.post("/wallet", data={"identifier": "+2348022223333"})
    assert f"Wallet {code1}" in by_phone.text


def test_explicit_wallet_code_links_a_new_report_to_an_existing_wallet(client, moderator_auth):
    first_code = _submit_and_approve(
        client, moderator_auth, description="explicit-code-1", award_points=100
    )
    second_code = _submit_and_approve(
        client, moderator_auth, description="explicit-code-2", wallet_code=first_code, award_points=50
    )
    assert second_code == first_code

    lookup = client.post("/wallet", data={"identifier": first_code})
    assert _wallet_balance(lookup.text) == 150  # 100 + 50 from both reports


def test_wallet_not_found_shows_a_message(client):
    response = client.post("/wallet", data={"identifier": "NOSUCHCODE"})
    assert response.status_code == 200
    assert "No wallet found" in response.text


def test_redeem_deducts_points_and_requires_contact_phone(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="redeem-marker", award_points=500)

    # Find the cheapest reward option's id + cost from the catalog page.
    lookup = client.post("/wallet", data={"identifier": code})
    option_id = re.search(r'name="reward_option_id" value="(\d+)"', lookup.text).group(1)
    balance_before = _wallet_balance(lookup.text)

    redeem = client.post(
        f"/wallet/{code}/redeem",
        data={"reward_option_id": option_id, "contact_phone": "+2348099998888"},
    )
    assert redeem.status_code == 200
    assert "Redemption requested" in redeem.text
    assert _wallet_balance(redeem.text) < balance_before


def test_redeem_without_enough_points_fails(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="poor-marker", award_points=0)
    lookup = client.post("/wallet", data={"identifier": code})
    option_id = re.search(r'name="reward_option_id" value="(\d+)"', lookup.text)
    # With 0 points, no redeem form should even be rendered for any option.
    assert option_id is None


def test_moderator_can_fulfill_a_redemption(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="fulfill-marker", award_points=1000)
    lookup = client.post("/wallet", data={"identifier": code})
    option_id = re.search(r'name="reward_option_id" value="(\d+)"', lookup.text).group(1)
    client.post(
        f"/wallet/{code}/redeem",
        data={"reward_option_id": option_id, "contact_phone": "+2348011112222"},
    )

    admin_queue = client.get("/redemptions", auth=moderator_auth)
    assert admin_queue.status_code == 200
    assert "+2348011112222" in admin_queue.text

    redemption_id = re.findall(r"/redemptions/(\d+)/fulfilled", admin_queue.text)[-1]
    fulfill = client.post(
        f"/redemptions/{redemption_id}/fulfilled",
        data={"notes": "sent"},
        auth=moderator_auth,
        follow_redirects=False,
    )
    assert fulfill.status_code == 303

    updated = client.get("/redemptions", auth=moderator_auth)
    assert "Fulfilled" in updated.text


def test_cancelling_a_redemption_refunds_points(client, moderator_auth):
    code = _submit_and_approve(client, moderator_auth, description="cancel-marker", award_points=1000)
    lookup = client.post("/wallet", data={"identifier": code})
    option_id = re.search(r'name="reward_option_id" value="(\d+)"', lookup.text).group(1)
    balance_before_redeem = _wallet_balance(lookup.text)

    client.post(
        f"/wallet/{code}/redeem",
        data={"reward_option_id": option_id, "contact_phone": "+2348011113333"},
    )
    balance_after_redeem = _wallet_balance(client.post("/wallet", data={"identifier": code}).text)
    assert balance_after_redeem < balance_before_redeem

    admin_queue = client.get("/redemptions", auth=moderator_auth)
    redemption_id = re.findall(r"/redemptions/(\d+)/cancelled", admin_queue.text)[-1]
    client.post(
        f"/redemptions/{redemption_id}/cancelled",
        data={"notes": "out of stock"},
        auth=moderator_auth,
        follow_redirects=False,
    )

    balance_after_cancel = _wallet_balance(client.post("/wallet", data={"identifier": code}).text)
    assert balance_after_cancel == balance_before_redeem  # fully refunded

    updated = client.get("/redemptions", auth=moderator_auth)
    assert "Cancelled" in updated.text


def test_redemptions_admin_requires_auth(client):
    assert client.get("/redemptions").status_code == 401

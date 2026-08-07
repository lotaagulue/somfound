from somfound.models import Category, Urgency, Village
from somfound.sms_parser import parse_sms

VILLAGES = [Village(id=1, name="Umuoji", lga="Idemili North", lat=6.12, lon=6.78)]


def test_recognized_keyword_sets_category_and_urgency():
    parsed = parse_sms("WATER Umuoji borehole broken 3 days no fix", VILLAGES)
    assert parsed.category == Category.NEEDS_RESOURCES
    assert parsed.urgency == Urgency.HIGH
    assert parsed.keyword_matched
    assert "borehole" in parsed.description
    assert parsed.village is not None
    assert parsed.village.name == "Umuoji"


def test_escalation_word_bumps_urgency():
    parsed = parse_sms("ROAD bridge collapsed urgent send help now", VILLAGES)
    # ROAD alone is moderate; "urgent"/"now" should escalate it up a notch.
    assert parsed.urgency == Urgency.HIGH


def test_unrecognized_text_falls_back_to_other():
    parsed = parse_sms("just checking in, nothing urgent", VILLAGES)
    assert parsed.category == Category.OTHER
    assert not parsed.keyword_matched


def test_empty_text_does_not_crash():
    parsed = parse_sms("   ", VILLAGES)
    assert parsed.category == Category.OTHER
    assert parsed.village is None


def test_village_match_is_case_insensitive():
    parsed = parse_sms("SCHOOL new block opened in umuoji today", VILLAGES)
    assert parsed.village is not None
    assert parsed.village.name == "Umuoji"

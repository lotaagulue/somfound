from somfound.models import LGA, Category, Urgency
from somfound.sms_parser import parse_sms

LGAS = [LGA(id=1, name="Nsukka", state="Enugu", lat=6.86, lon=7.40)]


def test_recognized_keyword_sets_category_and_urgency():
    parsed = parse_sms("WATER Nsukka borehole broken 3 days no fix", LGAS)
    assert parsed.category == Category.NEEDS_RESOURCES
    assert parsed.urgency == Urgency.HIGH
    assert parsed.keyword_matched
    assert "borehole" in parsed.description
    assert parsed.lga is not None
    assert parsed.lga.name == "Nsukka"


def test_escalation_word_bumps_urgency():
    parsed = parse_sms("ROAD bridge collapsed urgent send help now", LGAS)
    # ROAD alone is moderate; "urgent"/"now" should escalate it up a notch.
    assert parsed.urgency == Urgency.HIGH


def test_unrecognized_text_falls_back_to_other():
    parsed = parse_sms("just checking in, nothing urgent", LGAS)
    assert parsed.category == Category.OTHER
    assert not parsed.keyword_matched


def test_empty_text_does_not_crash():
    parsed = parse_sms("   ", LGAS)
    assert parsed.category == Category.OTHER
    assert parsed.lga is None


def test_lga_match_is_case_insensitive():
    parsed = parse_sms("SCHOOL new block opened in nsukka today", LGAS)
    assert parsed.lga is not None
    assert parsed.lga.name == "Nsukka"


def test_longest_lga_name_wins_on_substring_collision():
    lgas = [
        LGA(id=1, name="Isiala Ngwa North", state="Abia", lat=5.39, lon=7.45),
        LGA(id=2, name="Isiala Ngwa South", state="Abia", lat=5.36, lon=7.40),
    ]
    parsed = parse_sms("ROAD damaged in Isiala Ngwa South after rain", lgas)
    assert parsed.lga is not None
    assert parsed.lga.name == "Isiala Ngwa South"

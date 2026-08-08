from somfound.models import LGA, Category, Urgency
from somfound.sms_parser import guess_category_urgency, parse_sms

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


# --- guess_category_urgency (web form's freeform-sentence auto-categorization) ---


def test_guess_matches_keyword_anywhere_in_a_natural_sentence():
    category, urgency, matched = guess_category_urgency(
        "There was an armed robbery last night, please send crime officers"
    )
    assert category == Category.CRIME_SAFETY
    assert urgency == Urgency.CRITICAL  # HIGH from CRIME, escalated by "armed"
    assert matched


def test_guess_avoids_substring_false_positive():
    # "broadband" contains "road" as a substring — must not match ROAD.
    category, urgency, matched = guess_category_urgency(
        "The broadband service in our village has been down for a week"
    )
    assert category == Category.OTHER
    assert not matched


def test_guess_earliest_keyword_in_reading_order_wins():
    category, _, matched = guess_category_urgency(
        "The road by the school has been blocked, and there was also a crime committed nearby"
    )
    assert matched
    assert category == Category.INFRASTRUCTURE  # "road" appears before "crime"


def test_guess_escalation_word_still_bumps_urgency():
    category, urgency, matched = guess_category_urgency("The road is blocked, this is urgent")
    assert matched
    assert category == Category.INFRASTRUCTURE
    assert urgency == Urgency.HIGH  # ROAD's default MODERATE, escalated by "urgent"


def test_guess_falls_back_to_other_like_sms_does():
    category, urgency, matched = guess_category_urgency("Just wanted to say hello to everyone")
    assert category == Category.OTHER
    assert urgency == Urgency.MODERATE
    assert not matched

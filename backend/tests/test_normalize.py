from datetime import UTC, date, datetime

import pytest

from reviewring.normalize import dates, geo, text
from reviewring.normalize.geo import AreaPoint, area_from_address, assign_areas


@pytest.mark.parametrize(
    "s,lo,hi",
    [
        ("just now", 0, 1),
        ("a minute ago", 0, 1),
        ("5 minutes ago", 0, 1),
        ("an hour ago", 0, 1),
        ("3 hours ago", 0, 1),
        ("a day ago", 1, 2),
        ("4 days ago", 4, 5),
        ("a week ago", 7, 14),
        ("3 weeks ago", 21, 28),
        ("a month ago", 30, 60),
        ("5 months ago", 150, 180),
        ("a year ago", 365, 730),
        ("2 years ago", 730, 1095),
        ("Edited 2 weeks ago", 14, 21),
    ],
)
def test_relative_table(s, lo, hi):
    r = dates.parse_relative(s)
    assert (r.min_days, r.max_days) == (lo, hi)
    assert r.edited == s.startswith("Edited")


def test_unparseable_is_unknown():
    assert dates.parse_relative("sometime last spring") is None
    rng = dates.absolute_range("sometime", datetime(2026, 9, 28, tzinfo=UTC))
    assert not rng.known and rng.precision_days is None


def test_absolute_dates_use_ist_and_own_fetch_time():
    # 20:00 UTC on Sep 27 is already Sep 28 in IST.
    rng = dates.absolute_range("3 days ago", datetime(2026, 9, 27, 20, 0, tzinfo=UTC))
    assert (rng.date_min, rng.date_max) == (date(2026, 9, 24), date(2026, 9, 25))
    assert rng.precision_days == 1


def test_photo_date_narrows_the_range():
    fetched = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
    rng = dates.absolute_range("a month ago", fetched, ["2026-08-20", "2026-08-10", "2025-01-01"])
    assert rng.date_min == date(2026, 8, 20) and rng.date_max == date(2026, 8, 29)


def test_metro_aliases_merge():
    a = area_from_address("Sector 29, Gurugram, Haryana 122001")
    b = area_from_address("Connaught Place, New Delhi, Delhi 110001, India")
    c = area_from_address("Sector 18, Noida, Uttar Pradesh 201301")
    assert a == b == c == "Delhi NCR"
    assert area_from_address("MG Road, Bangalore, Karnataka 560001") == "Bengaluru"
    assert area_from_address("Ghodbunder Rd, Thane West, Thane, Maharashtra 400615") == "Mumbai"


def test_multi_word_states():
    assert area_from_address("Anna Nagar, Chennai, Tamil Nadu 600040") == "Chennai"
    assert area_from_address("Hazratganj, Lucknow, Uttar Pradesh 226001") == "Lucknow"
    assert area_from_address("Mall Road, Srinagar, Jammu and Kashmir 190001") == "Srinagar"
    assert area_from_address("Salt Lake, Kolkata, West Bengal 700091") == "Kolkata"


def test_non_indian_addresses():
    assert area_from_address("Sheikh Zayed Rd - Dubai - United Arab Emirates") is None
    assert area_from_address("Al Barsha, Dubai, United Arab Emirates") == "Dubai, UAE"
    assert area_from_address("Thamel, Kathmandu 44600, Nepal") == "Kathmandu, Nepal"


def test_clustering_is_order_independent():
    pts = [
        AreaPoint("k1", "Pune", 18.52, 73.85),
        AreaPoint("k2", None, 18.60, 73.80),
        AreaPoint("k3", None, 26.90, 75.80),
        AreaPoint("k4", None, 26.95, 75.78),
    ]
    a = assign_areas(pts)
    b = assign_areas(list(reversed(pts)))
    assert a == b
    assert a["k2"] == "Pune" and a["k3"] == a["k4"] == "Unnamed area 1"


def test_haversine():
    assert geo.haversine_km(19.076, 72.8777, 28.6139, 77.209) == pytest.approx(1150, rel=0.02)


def test_translated_review_uses_original():
    r = {"snippet": "(Translated by Google) Very good doctor (Original) बहुत अच्छे डॉक्टर"}
    assert text.review_text(r) == "बहुत अच्छे डॉक्टर"
    r2 = {"extracted_snippet": {"original": "Original text", "translated": "Translated"}, "snippet": "x"}
    assert text.review_text(r2) == "Original text"
    assert text.review_text({"snippet": "(Translated by Google) Nice"}) == "Nice"


def test_devanagari_keeps_vowel_signs():
    n = text.normalize("बहुत अच्छे डॉक्टर!")
    assert "ु" in n and "े" in n and "!" not in n
    assert text.script_of("बहुत अच्छे") == "devanagari"
    assert text.script_of("Nice डॉक्टर") == "mixed"
    assert text.script_of("") == "none"


def test_near_duplicate_threshold_and_min_length():
    base = "Excellent service and very caring staff, highly recommended to everyone"
    edited = "Excellent service and very caring staff, highly recommend to everyone"
    other = "Parking was difficult but the food made up for it completely"
    items = [
        text.TextItem("t:1", "a", base, True),
        text.TextItem("h:b:1", "b", edited, False),
        text.TextItem("h:c:1", "c", other, False),
        text.TextItem("t:2", "d", "Good place", True),
        text.TextItem("h:e:1", "e", "Good place", False),
        text.TextItem("h:a:2", "a", base, False),  # same owner: never paired with t:1
    ]
    f = text.near_duplicate_clusters(items)
    assert f["t:1"].cluster == f["h:b:1"].cluster is not None
    assert f["h:c:1"].cluster is None
    assert f["t:2"].cluster is None and f["t:2"].short  # too short to be a near-duplicate
    assert f["h:a:2"].cluster is None

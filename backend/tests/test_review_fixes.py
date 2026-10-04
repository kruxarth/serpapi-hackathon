"""Scenarios raised by the external design review (docs/SYSTEM-OVERVIEW.md, section 11)."""

from datetime import timedelta

from reviewring.engine.analyze import analyze
from reviewring.engine.features import compute_text_features
from reviewring.engine.homes import compute_homes
from reviewring.engine.priority import score_reviews
from reviewring.engine.target_signals import detect_bursts
from reviewring.parse import contributor_history
from reviewring.synth import FETCHED, World, ordinary_reviewers, plant_ring


def group_of(report, cid):
    return next((g for g in report["groups"] if cid in g["members"]), None)


def label_of(report, cid):
    return next(r["label"] for r in report["reviews"] if r["contributor_id"] == cid)


def hometown_friends(w: World, n=5, home="Pune", extra_far=None):
    """College friends from one city who all reviewed the target, sharing places at home."""
    shared = [w.place(home, t, near_km=6) for t in ("College", "Cafe", "Restaurant")]
    if extra_far:
        shared.append(w.place(extra_far, "Dhaba"))
    ids = []
    for _ in range(n):
        cid = w.reviewer(total=50, photos=10)
        for p in shared:
            w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=w.rng.randint(30, 600))
        w.personal_history(cid, home, 15)
        w.review_target(cid, rating=5)
        ids.append(cid)
    return ids


def test_hometown_friends_at_a_far_resort_are_not_a_ring():
    w = World(target_city="Goa", target_type="Resort")
    ordinary_reviewers(w, 15, home="Goa")
    friends = hometown_friends(w, extra_far="Mumbai")
    r = analyze(w.build())
    g = group_of(r, friends[0])
    assert g is None or g["verdict"] in ("social_circle", "none")
    assert all(label_of(r, f) not in ("ring", "possible_ring_trip", "suspicious") for f in friends)
    assert r["level"]["level"] == "Low"


def test_homes_come_from_personal_places_only():
    w = World(target_city="Goa", target_type="Resort")
    friends = hometown_friends(w)
    farm = plant_ring(w, 4, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    homes = compute_homes(w.build(), friends + farm)
    assert all(homes[f].area == "Pune" for f in friends)
    assert not any(c in homes for c in farm)  # histories are all shared clients: no home


def test_farm_members_with_different_homes_are_still_a_ring():
    w = World()
    ordinary_reviewers(w, 10)
    ring = plant_ring(w, 6, cities=["Jaipur", "Kochi", "Lucknow"], m=4, thin=False)
    for cid, home in zip(ring, ["Kolkata", "Chennai", "Indore", "Nagpur", "Ahmedabad", "Hyderabad"], strict=True):
        w.personal_history(cid, home, 12)  # real people in different cities
    r = analyze(w.build())
    assert group_of(r, ring[0])["verdict"] == "ring"


def test_regional_campaign_without_trip_evidence_stays_visible():
    """Aged accounts, a 4/5-star mix, one week: trip-like shape with all three indicators, but no shared home
    and no travel-party details, so it must not be ruled out."""
    w = World(target_city="Jaipur", target_type="Hotel")
    ordinary_reviewers(w, 15, home="Jaipur")
    hotels = [
        w.place(c, t)
        for c, t in (("Udaipur", "Hotel"), ("Jodhpur", "Resort"), ("Udaipur", "Restaurant"), ("Jodhpur", "Hotel"))
    ]
    members = []
    for home in ["Kolkata", "Chennai", "Indore", "Nagpur", "Lucknow"]:
        cid = w.reviewer(total=80, photos=30)
        for p in hotels:
            w.add_history(cid, p, w.rng.choice((4, 5)), days_ago=20, precision="week")
        w.personal_history(cid, home, 25)
        w.review_target(cid, rating=5)
        members.append(cid)
    r = analyze(w.build())
    g = group_of(r, members[0])
    assert g["trip"]["indicators_met"] >= 2 and not any(g["trip"]["positive_evidence"].values())
    assert g["verdict"] == "possible_ring_trip"
    assert r["level"]["level"] == "Elevated"


def test_travel_party_details_count_as_trip_evidence():
    w = World(target_city="Jaipur", target_type="Hotel")
    ordinary_reviewers(w, 15, home="Jaipur")
    stops = [w.place(c, t) for c, t in (("Udaipur", "Hotel"), ("Jodhpur", "Resort"), ("Udaipur", "Restaurant"))]
    members = []
    for home in ["Kolkata", "Chennai", "Indore", "Nagpur"]:  # friends from different cities, one trip
        cid = w.reviewer()
        for p in stops:
            h = w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=20, precision="week")
            h.travel_group = "friends"
        w.personal_history(cid, home, 25)
        w.review_target(cid, rating=4)
        members.append(cid)
    g = group_of(analyze(w.build()), members[0])
    assert g["trip"]["positive_evidence"]["travel_party"] and g["verdict"] == "ruled_out_trip"


def test_one_non_travel_core_place_keeps_the_trip_shape():
    w = World(target_city="Jaipur", target_type="Hotel")
    ordinary_reviewers(w, 15, home="Jaipur")
    stops = [
        w.place("Udaipur", "Hotel"),
        w.place("Udaipur", "Restaurant"),
        w.place("Jodhpur", "Resort"),
        w.place("Jodhpur", "Handicraft store"),
    ]  # the tour guide's emporium
    members = []
    for _ in range(5):
        cid = w.reviewer()
        for p in stops:
            w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=20, precision="week")
        w.personal_history(cid, "Mumbai", 25)
        w.review_target(cid, rating=4)
        members.append(cid)
    g = group_of(analyze(w.build()), members[0])
    assert g["trip"]["trip_like_shape"] and g["verdict"] == "ruled_out_trip"


def test_travel_group_is_parsed_from_details():
    body = {
        "contributor": {"name": "x"},
        "reviews": [
            {
                "review_id": "1",
                "rating": 5,
                "date": "2 weeks ago",
                "snippet": "Nice stay",
                "details": {"Trip_type": "Vacation", "Travel_group": "Family"},
                "place_info": {"title": "H", "data_id": "0x1:0x2", "type": "Hotel"},
            },
        ],
    }
    _, history, _ = contributor_history(body, "c1", FETCHED)
    assert history[0].travel_group == "family"
    assert history[0].text == "Nice stay"  # contributor reviews carry text in `snippet`


def test_small_batches_raise_priority():
    w = World(total_reviews=5000)
    ordinary_reviewers(w, 40)
    t = FETCHED - timedelta(days=9)
    batch = []
    for i in range(3):
        cid = w.reviewer(total=60, photos=20)
        w.review_target(cid, rating=5, when=t + timedelta(hours=i * 5))
        batch.append(cid)
    inp = w.build()
    cands = score_reviews(inp.target_reviews, detect_bursts(inp.target_reviews), compute_text_features(inp))
    parts = {c.contributor_id: c.parts for c in cands}
    assert all("batch" in parts[c] for c in batch)


def test_farm_template_with_few_checked_users_is_not_a_stock_phrase():
    w = World()
    ordinary_reviewers(w, 15)
    template = "Wonderful staff and excellent service, very professional, highly recommended to all"
    users = []
    for _ in range(12):
        cid = w.reviewer()
        w.review_target(cid, rating=5, text=template)
        users.append(cid)
    inp = w.build()
    unchecked = set(users[2:])  # 12 accounts use the template, but only 2 of them get checked
    inp.expansions = [e for e in inp.expansions if e.contributor_id not in unchecked]
    report = analyze(inp)
    assert report["signals"]["T4"]["stock_phrase_clusters"] == []
    assert report["signals"]["T4"]["clusters"]  # kept as evidence

    inp.expansions = w.build().expansions  # all 12 checked and unconnected: now it is a stock phrase
    assert analyze(inp)["signals"]["T4"]["stock_phrase_clusters"]


def test_date_calibration_pairs():
    w = World()
    ordinary_reviewers(w, 5)
    rows = analyze(w.build())["calibration"]
    assert len(rows) == 5 and all({"relative", "true_date", "inside"} <= set(r) for r in rows)


def test_targeted_without_knowledge_caveat():
    w = World()
    ordinary_reviewers(w, 5)
    assert any("without its knowledge" in c for c in analyze(w.build())["caveats"])


def test_fixture_dates_shift_but_intervals_stay():
    from reviewring.exporter import build_fixture, input_from_dict

    w = World(total_reviews=640)
    ordinary_reviewers(w, 12)
    inp = w.build()
    fixture = build_fixture(inp, "x", title="x", salt_value="s")
    out = input_from_dict(fixture["input"])
    orig = sorted(r.posted_at for r in inp.target_reviews)
    moved = sorted(r.posted_at for r in out.target_reviews)
    shift = orig[0] - moved[0]
    assert timedelta(days=30) <= shift <= timedelta(days=366)
    assert all(o - m == shift for o, m in zip(orig, moved, strict=True))
    assert out.target.total_reviews == 600
    assert all(p.lat is None or round(p.lat, 1) == p.lat for p in out.places.values())


def test_presentation_mode_shifts_dates_and_rounds():
    from reviewring.privacy import pseudonymize_report

    w = World(total_reviews=2345)
    ordinary_reviewers(w, 10)
    plant_ring(w, 5, cities=["Jaipur", "Kochi", "Lucknow"], m=3)
    report = analyze(w.build())
    shown = pseudonymize_report(report, salt_value="s")
    assert shown["dates_shifted"] and shown["place"]["total_reviews"] == 2000
    assert shown["sample"]["first"] != report["sample"]["first"]
    assert all("date" not in row for row in shown["reviews"])
    assert all(round(p["lat"], 1) == p["lat"] for p in shown["places"].values() if p["lat"] is not None)


def test_burst_of_single_use_accounts_raises_level_to_elevated():
    w = World(total_reviews=900)
    ordinary_reviewers(w, 40)
    t = FETCHED - timedelta(days=30)
    burners = []
    for i in range(12):
        cid = w.reviewer(total=1, photos=0)
        w.histories[cid] = []  # the account's only review is this business
        r = w.review_target(cid, rating=5, when=t + timedelta(hours=i * 3), total=1, photos=0)
        burners.append(r.review_id)
    inp = w.build()
    report = analyze(inp)
    t6 = report["signals"]["T6"]["single_use_bursts"]
    assert any(b["flagged"] and b["single_use"] >= 10 for b in t6)
    assert report["level"]["level"] == "Elevated"
    labels = {r["review_id"]: r["label"] for r in report["reviews"]}
    assert sum(labels[b] == "single_use_burst" for b in burners) >= 10
    assert any(e["kind"] == "single_use_burst" for e in report["evidence"])


def test_burst_of_established_accounts_does_not_raise_level():
    w = World(total_reviews=900)
    ordinary_reviewers(w, 40)
    t = FETCHED - timedelta(days=30)
    for i in range(12):
        cid = w.reviewer(total=40, photos=10)
        w.review_target(cid, rating=5, when=t + timedelta(hours=i * 3))
    report = analyze(w.build())
    assert not any(b["flagged"] for b in report["signals"]["T6"]["single_use_bursts"])
    assert report["level"]["level"] == "Low"

"""Scenarios raised by the external design review."""

from datetime import timedelta

from reviewring.engine.analyze import analyze
from reviewring.engine.features import compute_text_features
from reviewring.engine.homes import compute_homes
from reviewring.engine.priority import score_reviews
from reviewring.engine.target_signals import detect_bursts
from reviewring.parse import contributor_history
from reviewring.privacy import pseudonymize_report
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


def burst_world(n=16, *, stars=5, every=timedelta(minutes=5), total=1, alternate=None):
    """40 ordinary reviews over four months, plus `n` reviews packed together a month ago."""
    w = World(total_reviews=900)
    ordinary_reviewers(w, 40)
    t = FETCHED - timedelta(days=30)
    ids = []
    for i in range(n):
        cid = w.reviewer(total=total, photos=0)
        if total == 1:
            w.histories[cid] = []  # the account's only review is this business
        rating = alternate if alternate and i % 2 else stars
        ids.append(w.review_target(cid, rating=rating, when=t + every * i, total=total, photos=0).review_id)
    return w, ids


def test_a_burst_of_five_star_reviews_is_told_in_minutes_and_raises_the_level():
    w, ids = burst_world()
    report = analyze(w.build())
    flagged = [c for c in report["signals"]["T11"]["clusters"] if c["flagged"]]
    assert len(flagged) == 1 and set(ids) <= set(flagged[0]["review_ids"]) and 75 <= flagged[0]["minutes"] < 90
    c0 = flagged[0]
    assert c0["first_time"] == 16 and c0["pace"] >= 10 and len(c0["offsets"]) == c0["count"]
    assert report["level"]["level"] == "Elevated"
    assert any(f"{flagged[0]['count']} five-star reviews arrived in" in x for x in report["level"]["reasons"])
    labels = {r["review_id"]: r for r in report["reviews"]}
    assert all("review_burst" in labels[i]["signs"] and labels[i]["label"] == "single_use_burst" for i in ids)
    assert any(e["kind"] == "review_burst" for e in report["evidence"])
    shown = pseudonymize_report(report, salt_value="s")
    c = next(c for c in shown["signals"]["T11"]["clusters"] if c["flagged"])
    assert set(c["review_ids"]) <= {r["review_id"] for r in shown["reviews"]} and c["start"] != flagged[0]["start"]
    assert c["offsets"] == flagged[0]["offsets"] and c["start"][11:] == flagged[0]["start"][11:]  # days shift only


def test_established_accounts_count_too_and_one_star_attacks_are_flagged():
    w, _ = burst_world(total=40)
    report = analyze(w.build())
    c = next(c for c in report["signals"]["T11"]["clusters"] if c["flagged"])
    assert c["first_time"] == 0 and report["level"]["level"] == "Elevated"
    w, ids = burst_world(stars=1, every=timedelta(minutes=8))
    report = analyze(w.build())
    c = next(c for c in report["signals"]["T11"]["clusters"] if c["flagged"])
    assert c["stars"] == 1 and set(ids) <= set(c["review_ids"])
    assert any("16 one-star reviews" in x for x in report["level"]["reasons"])


def test_a_slow_trickle_mixed_stars_or_a_busy_listing_is_not_a_burst():
    for w, _ in (burst_world(every=timedelta(hours=12)), burst_world(alternate=4)):
        assert not any(c["flagged"] for c in analyze(w.build())["signals"]["T11"]["clusters"])
    busy = World(total_reviews=5000)  # the newest 100 reviews span three days
    for i in range(100):
        cid = busy.reviewer(total=10, photos=1)
        busy.review_target(cid, rating=5 if i % 3 else 4, when=FETCHED - timedelta(minutes=43 * i))
    clusters = analyze(busy.build())["signals"]["T11"]["clusters"]
    assert clusters and not any(c["flagged"] for c in clusters)  # most reviews are 5★ there, at the usual pace


def test_rating_gap_top_rated_sample_and_generated_text():
    from reviewring.model import TargetReview

    w = World(total_reviews=5000, rating=4.9)
    ordinary_reviewers(w, 60, rating_pool=(1, 2, 3, 4, 5))
    inp = w.build()
    old = FETCHED - timedelta(days=600)
    inp.top_rated = [
        TargetReview(
            f"top{i}",
            f"old{i}",
            5,
            old + timedelta(days=i),
            text="Lovely stay, great staff and rooms",
            reviewer_reviews=1,
            reviewer_photos=0,
        )
        for i in range(20)
    ]
    inp.top_rated.append(
        TargetReview(
            "topx",
            "oldx",
            5,
            old,
            text="I'm unable to generate a review for you, but I can help you outline key points.",
            reviewer_reviews=2,
            reviewer_photos=0,
        )
    )
    r = analyze(inp)
    gap = r["signals"]["T7"]
    assert gap["flagged"] and gap["older_implied_mean"] > 4.9 > gap["recent_mean"]
    top = r["signals"]["T8"]
    assert top["window_count"] == 21 and top["single_use_share"] > 0.9
    assert top["generated"][0]["marker"] == "unable to generate"
    assert r["level"]["level"] == "Elevated"
    kinds = {e["kind"] for e in r["evidence"]}
    assert {"rating_gap", "top_rated", "generated_text"} <= kinds


def test_needs_top_rated_only_for_a_large_gap():
    from reviewring.collect import needs_top_rated

    w = World(total_reviews=5000, rating=4.9)
    ordinary_reviewers(w, 40, rating_pool=(1, 2, 3))
    assert needs_top_rated(w.build())
    w2 = World(total_reviews=5000, rating=4.2)
    ordinary_reviewers(w2, 40, rating_pool=(4, 5))
    assert not needs_top_rated(w2.build())


def test_presentation_mode_blurs_counts_and_dates_inside_sentences():
    from reviewring.model import TargetReview
    from reviewring.privacy import pseudonymize_report

    w = World(total_reviews=6607, rating=4.9)
    ordinary_reviewers(w, 60, rating_pool=(1, 2, 3, 4, 5))
    inp = w.build()
    inp.top_rated = [
        TargetReview(f"t{i}", f"o{i}", 5, FETCHED - timedelta(days=600 + i), text="ok fine", reviewer_reviews=1)
        for i in range(10)
    ]
    report = analyze(inp)
    text = " ".join(e["text"] for e in report["evidence"])
    assert "6,607" in text
    shown = pseudonymize_report(report, salt_value="s")
    shown_text = " ".join(e["text"] for e in shown["evidence"]) + " ".join(shown["level"]["reasons"])
    assert "6,607" not in shown_text and "about 7,000" in shown_text
    for d in __import__("re").findall(r"\d{4}-\d{2}-\d{2}", text):
        assert d not in shown_text


def test_presentation_mode_pseudonymizes_reviewer_histories():
    from reviewring.privacy import pseudonymize_report

    w = World()
    ordinary_reviewers(w, 10)
    plant_ring(w, 5, cities=["Jaipur", "Kochi", "Lucknow"], m=3)
    inp = w.build()
    report = analyze(inp)
    assert report["histories"] and set(report["histories"]) <= {e.contributor_id for e in inp.expansions}
    shown = pseudonymize_report(report, salt_value="s")
    text = repr(shown["histories"])
    for cid in report["histories"]:
        assert cid not in text
    for h in report["histories"].values():
        for it in h["items"]:
            assert it["place_key"] is None or it["place_key"] not in text
    items = [it for h in shown["histories"].values() for it in h["items"]]
    assert all(it["lat"] is None or round(it["lat"], 1) == it["lat"] for it in items)
    assert items[0]["day"] != next(iter(report["histories"].values()))["items"][0]["day"]


def test_chatbot_excerpt_is_kept_and_scrubbed():
    from reviewring.privacy import pseudonymize_report

    w = World()
    ordinary_reviewers(w, 20)
    cid = w.reviewer()
    w.personal_history(cid, "Pune", 4)
    w.review_target(cid, rating=5, text="I'm unable to generate a review for you, but call 9876543210 for help.")
    report = analyze(w.build())
    row = next(r for r in report["reviews"] if r["generated_marker"])
    assert row["excerpt"].startswith("I'm unable to generate")
    shown = pseudonymize_report(report, salt_value="s")
    srow = next(r for r in shown["reviews"] if r["generated_marker"])
    assert "unable to generate" in srow["excerpt"] and "9876543210" not in srow["excerpt"]


def test_presentation_mode_hides_short_business_names_and_the_neighbourhood():
    import json

    from reviewring.privacy import business_terms, pseudonymize_report, scrub_text

    from .test_signs import keyword_world

    assert business_terms("Om Sai Packers And Movers") >= {"Om Sai", "Sai", "Packers", "Movers"}
    assert "And" not in business_terms("Om Sai Packers And Movers")
    assert scrub_text("Thanks om-sai packers, Hadapsar!", business_terms("Om Sai Packers"), {"hadapsar"}) == (
        "Thanks [business] [business], [area]!"
    )
    w, _ = keyword_world()
    report = analyze(w.build())
    assert {"hadapsar", "maharashtra"} <= set(report["place"]["locality"]) and "pune" not in report["place"]["locality"]
    shown = pseudonymize_report(report, salt_value="s")
    dump = json.dumps(shown).casefold()
    assert "shanti" not in dump and "hadapsar" not in dump and "locality" not in dump
    assert "[area]" in dump  # the copied texts are kept, with the neighbourhood scrubbed

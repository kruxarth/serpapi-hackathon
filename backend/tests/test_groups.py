"""Hand-built group scenarios from spec section 15."""

from reviewring.engine.analyze import analyze
from reviewring.engine.groups import confidence, type_group
from reviewring.synth import World, ordinary_reviewers, plant_ring


def verdicts(report):
    return [(g["verdict"], len(g["members"])) for g in report["groups"]]


def group_of(report, cid):
    return next((g for g in report["groups"] if cid in g["members"]), None)


def trip(world, n, places, *, ordinary=True, precision="week", ratings=(3, 4, 5), days_ago=60, home="Pune"):
    """n people who all reviewed the given places on one trip."""
    members = []
    for _ in range(n):
        cid = world.reviewer(total=60 if ordinary else 4, photos=20 if ordinary else 0)
        for p in places:
            world.add_history(cid, p, world.rng.choice(ratings), days_ago=days_ago, precision=precision)
        if ordinary:
            world.personal_history(cid, home, 25)
        world.review_target(cid, rating=world.rng.choice((4, 5)))
        members.append(cid)
    return members


def test_clear_ring():
    w = World()
    ordinary_reviewers(w, 10)
    ring = plant_ring(w, 8, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    r = analyze(w.build())
    assert verdicts(r)[0] == ("ring", 8)
    assert r["level"]["level"] == "High"
    assert all(row["label"] == "ring" for row in r["reviews"] if row["contributor_id"] in ring)


def test_no_ring():
    w = World()
    ordinary_reviewers(w, 20)
    r = analyze(w.build())
    assert not [g for g in r["groups"] if g["verdict"] != "none"]
    assert r["level"]["level"] == "Low"


def test_borderline_three_accounts_is_possible_ring():
    w = World()
    ordinary_reviewers(w, 10)
    plant_ring(w, 3, cities=["Jaipur", "Kochi"], m=3)
    r = analyze(w.build())
    assert verdicts(r)[0] == ("possible_ring", 3)
    assert r["level"]["level"] == "Elevated"  # a possible ring can never make it High


def test_wedding_party_is_not_a_ring():
    w = World()
    ordinary_reviewers(w, 10)
    venue = [w.place("Jaipur", "Wedding venue"), w.place("Jaipur", "Hotel"), w.place("Jaipur", "Restaurant")]
    trip(w, 12, venue, precision="week")
    r = analyze(w.build())
    assert all(v not in ("ring", "possible_ring") for v, _ in verdicts(r))


def test_tour_through_two_nearby_states_is_ruled_out():
    w = World()
    ordinary_reviewers(w, 10)
    tour = [w.place("Udaipur", "Hotel"), w.place("Udaipur", "Hindu temple"), w.place("Udaipur", "Restaurant"),
            w.place("Ahmedabad", "Hotel"), w.place("Ahmedabad", "Cafe")]
    members = trip(w, 6, tour)
    r = analyze(w.build())
    g = group_of(r, members[0])
    assert g is not None and g["verdict"] == "ruled_out_trip"
    assert r["level"]["level"] == "Low"
    assert all(row["label"] == "group_trip" for row in r["reviews"] if row["contributor_id"] in members)


def test_country_wide_hotel_task_scam_is_a_ring():
    w = World()
    ordinary_reviewers(w, 10)
    ring = plant_ring(w, 6, cities=["Goa", "Kolkata", "Delhi NCR", "Kochi"], m=4, types=["Hotel", "Resort"])
    r = analyze(w.build())
    g = group_of(r, ring[0])
    assert g["verdict"] == "ring" and g["trip"]["trip_like_shape"] is False


def test_local_circle_is_not_a_ring():
    w = World()
    ordinary_reviewers(w, 10)
    spots = [w.place("Pune", t, near_km=3) for t in ("Cafe", "Restaurant", "Gym", "Bakery", "Bookstore", "Salon")]
    friends = []
    for _ in range(6):
        cid = w.reviewer()
        for p in spots:
            w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=w.rng.randint(5, 300), precision="day")
        w.personal_history(cid, "Pune", 10)
        w.review_target(cid)
        friends.append(cid)
    r = analyze(w.build())
    assert all(v in ("none", "ruled_out_trip") for v, _ in verdicts(r))


def test_large_loose_component_is_split_with_louvain():
    w = World()
    ordinary_reviewers(w, 10)
    a = plant_ring(w, 6, cities=["Jaipur", "Kochi", "Lucknow"], m=4, base_days_ago=30)
    b = plant_ring(w, 6, cities=["Kolkata", "Chennai", "Indore"], m=4, base_days_ago=90,
                   template="Wonderful staff and quick work, five stars from our family!")
    for x, y in ((a[0], b[0]), (a[1], b[1])):  # two cross edges, each through its own pair of places
        for p in (w.place("Nagpur", "Dental clinic"), w.place("Goa", "Car dealer")):
            w.add_history(x, p)
            w.add_history(y, p)
    r = analyze(w.build())
    rings = [g for g in r["groups"] if g["verdict"] == "ring"]
    assert sorted(len(g["members"]) for g in rings) == [6, 6]
    assert {frozenset(g["members"]) for g in rings} == {frozenset(a), frozenset(b)}


def test_outsider_attached_by_one_edge_is_pruned():
    w = World()
    ordinary_reviewers(w, 10)
    ring = plant_ring(w, 6, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    outsider = w.reviewer()
    w.personal_history(outsider, "Pune", 15)
    for p in (w.place("Nagpur", "Dental clinic"), w.place("Goa", "Car dealer")):  # shared with ring[0] only
        w.add_history(outsider, p, 4)
        w.add_history(ring[0], p, 5)
    w.review_target(outsider, rating=4)
    r = analyze(w.build())
    g = group_of(r, ring[0])
    assert g["verdict"] == "ring" and outsider not in g["members"] and outsider in g["pruned"]
    label = next(row["label"] for row in r["reviews"] if row["contributor_id"] == outsider)
    assert label != "ring"


def test_regional_hotel_ring_is_possible_ring_trip():
    w = World()
    ordinary_reviewers(w, 10)
    hotels = [w.place(c, t) for c, t in (("Jaipur", "Hotel"), ("Udaipur", "Resort"), ("Jodhpur", "Hotel"),
                                         ("Jaipur", "Restaurant"))]
    members = trip(w, 5, hotels, ordinary=False, precision="month", ratings=(5,))
    r = analyze(w.build())
    g = group_of(r, members[0])
    assert g["verdict"] == "possible_ring_trip" and g["trip"]["status"] == "unresolved"
    assert all(row["label"] == "possible_ring_trip" for row in r["reviews"] if row["contributor_id"] in members)
    assert r["level"]["level"] == "Elevated"
    assert r["ratings"]["without_ring"] == r["ratings"]["sample_mean"]  # not removed from the headline


def test_regional_group_trip_by_ordinary_people_is_ruled_out():
    w = World()
    ordinary_reviewers(w, 10)
    stops = [w.place(c, t) for c, t in (("Jaipur", "Hotel"), ("Udaipur", "Resort"), ("Jodhpur", "Hotel"),
                                        ("Jaipur", "Restaurant"))]
    members = trip(w, 6, stops, ordinary=True, precision="week", ratings=(2, 3, 4, 5))
    r = analyze(w.build())
    assert group_of(r, members[0])["verdict"] == "ruled_out_trip"


# ------------------------------------------------------------------ scoring


def test_confidence_with_unknown_timing_renormalizes():
    m = {"core_places": 6, "far_area_count": 4, "type_diversity": 4, "concentration": 0.3, "co_timing_ratio": None,
         "member_signal_share": 1.0}
    score, parts = confidence(m, 1.0)
    assert score == 1.0
    assert next(p for p in parts if p["part"] == "Timing")["used"] is False
    m2 = dict(m, co_timing_ratio=0.0)
    assert confidence(m2, 1.0)[0] == 0.85


def test_suspicious_needs_copied_text():
    w = World()
    ordinary_reviewers(w, 12)
    template = "Amazing doctor and caring staff, the best clinic experience I have ever had!"
    thin = []
    for _ in range(4):
        cid = w.reviewer(total=3, photos=0)
        w.personal_history(cid, "Pune", 2, ratings=(5,))
        w.review_target(cid, rating=5, text=template)
        thin.append(cid)
    lonely = w.reviewer(total=2, photos=0)
    w.review_target(lonely, rating=5, text="ok")
    r = analyze(w.build())
    labels = {row["contributor_id"]: row["label"] for row in r["reviews"]}
    assert all(labels[c] == "suspicious" for c in thin)
    assert labels[lonely] == "no_flags"  # thin and short, but no copied text


def test_young_business_without_ring():
    w = World(total_reviews=30)
    ordinary_reviewers(w, 12)
    assert analyze(w.build())["level"]["level"] == "Not enough history"


def test_adjusted_rating_range():
    w = World(total_reviews=100, rating=4.0)
    ordinary_reviewers(w, 20, rating_pool=(3, 4))
    plant_ring(w, 10, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    r = analyze(w.build())["ratings"]
    assert r["without_ring"] < r["sample_mean"]
    o = r["overall"]
    assert o["low"] == round((3.95 * 100 - 50) / 90, 2) and o["high"] == round((4.05 * 100 - 50) / 90, 2)
    assert o["no_visible_change"] is False


def test_all_private_is_not_low():
    w = World()
    ordinary_reviewers(w, 10)
    inp = w.build()
    for c in inp.contributors.values():
        c.status = "private"
    assert analyze(inp)["level"]["level"] == "Not enough history"


def test_type_groups():
    assert type_group("Hindu temple") == ("Tourist & religious", True)
    assert type_group("Sweet shop") == ("Food & drink", True)
    assert type_group("Hair transplantation clinic") == ("Health", False)
    assert type_group("Packers and movers") == ("Home & moving services", False)
    assert type_group(None) == ("Other", False)
    assert type_group("Barber shop")[0] == "Retail"  # "bar" must match whole words only


def test_deterministic():
    def run():
        w = World(seed=11)
        ordinary_reviewers(w, 30)
        plant_ring(w, 7, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
        return analyze(w.build())

    assert run() == run()

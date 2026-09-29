from datetime import UTC, datetime, timedelta

from reviewring.engine.features import compute_text_features
from reviewring.engine.graph import build_pairs, edges, is_popular_type, surprise
from reviewring.engine.priority import score_reviews, select_round1, select_round2
from reviewring.engine.target_signals import detect_bursts, rating_histogram, thin_profile_skew, young_business
from reviewring.model import Place, TargetReview
from reviewring.synth import World, ordinary_reviewers, plant_ring

T0 = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)


def rev(i, days_ago, rating=5, hours=0.0, **kw):
    return TargetReview(f"r{i:03d}", f"c{i:03d}", rating, T0 - timedelta(days=days_ago, hours=hours), **kw)


def steady(n=60, every_days=2.0, start=0):
    return [rev(start + i, i * every_days, rating=(i % 5) + 1) for i in range(n)]


def test_burst_that_dominates_the_sample_is_still_flagged():
    reviews = steady(20, 4.0)  # 20 reviews over ~80 days
    reviews += [rev(100 + i, 10, hours=i) for i in range(40)]  # 40 five-star reviews in ~2 days
    result = detect_bursts(reviews)
    assert not result.skipped
    assert len(result.bursts) == 1
    b = result.bursts[0]
    assert b.direction == "positive" and b.count >= 40 and b.matching >= 40


def test_burst_days_binned_in_ist():
    # 20:00 UTC on Sep 17 is Sep 18 in IST.
    reviews = steady(20, 4.0)
    reviews += [
        TargetReview(f"b{i}", f"b{i}", 5, datetime(2026, 9, 17, 20, 0, tzinfo=UTC) + timedelta(minutes=i))
        for i in range(12)
    ]
    [b] = detect_bursts(reviews).bursts
    assert b.start <= datetime(2026, 9, 18).date() <= b.end
    assert b.end < datetime(2026, 9, 21).date()


def test_negative_burst():
    reviews = steady(30, 3.0) + [rev(200 + i, 5, rating=1, hours=i) for i in range(15)]
    [b] = detect_bursts(reviews).bursts
    assert b.direction == "negative"


def test_mixed_ratings_spike_not_flagged():
    reviews = steady(30, 3.0) + [rev(200 + i, 5, rating=(i % 5) + 1, hours=i) for i in range(15)]
    assert detect_bursts(reviews).bursts == []


def test_skip_rules():
    assert detect_bursts(steady(9)).skipped
    same_day = [rev(i, 0, hours=i * 0.1) for i in range(20)]
    r = detect_bursts(same_day)
    assert r.skipped and "span" in r.reason


def test_busy_place_is_not_young():
    w = World(total_reviews=5000)
    w.target_reviews = [rev(i, i * 0.25) for i in range(88)]  # 88 reviews in 3 weeks
    inp = w.build()
    assert young_business(inp, detect_bursts(inp.target_reviews))["young"] is False
    w2 = World(total_reviews=40)
    w2.target_reviews = [rev(i, i * 10) for i in range(30)]
    inp2 = w2.build()
    assert young_business(inp2, detect_bursts(inp2.target_reviews))["young"] is True
    w3 = World(total_reviews=150)
    w3.target_reviews = [rev(i, i * 0.2) for i in range(88)]
    inp3 = w3.build()
    assert young_business(inp3, detect_bursts(inp3.target_reviews))["young"] is True


def test_histogram_and_thin_skew():
    rs = [
        rev(1, 1, 5, reviewer_reviews=2),
        rev(2, 2, 5, reviewer_reviews=50),
        rev(3, 3, 5),
        rev(4, 4, 2, reviewer_reviews=40),
    ]
    assert rating_histogram(rs) == {"1": 0, "2": 1, "3": 0, "4": 0, "5": 3}
    skew = thin_profile_skew(rs)
    assert skew["five_star"]["thin_share"] == 0.5 and skew["five_star"]["unknown"] == 1
    assert skew["low_star"]["thin_share"] == 0.0


def test_popular_type_matching():
    assert is_popular_type("Water park") and is_popular_type("Buddhist temple")
    assert is_popular_type("Tourist attraction") and is_popular_type("Shopping mall")
    assert not is_popular_type("Parking lot") and not is_popular_type("Police station")
    assert not is_popular_type(None) and not is_popular_type("Dental clinic")


def test_surprise_weights():
    t = Place("t", lat=18.52, lng=73.85)
    assert surprise(t, Place("a", lat=18.53, lng=73.85, type="Cafe")) == 0.2
    assert surprise(t, Place("b", lat=18.80, lng=73.85, type="Cafe")) == 0.5
    assert surprise(t, Place("c", lat=28.6, lng=77.2, type="Cafe")) == 1.0
    assert surprise(t, Place("d", lat=28.6, lng=77.2, type="Hindu temple")) == 0.1
    assert surprise(t, Place("e", type="Cafe")) == 0.5


def test_edges_need_two_far_non_popular_places_without_timing():
    w = World()
    a, b = w.reviewer(), w.reviewer()
    far1, far2 = w.place("Jaipur", "Dental clinic"), w.place("Kochi", "Packers and movers")
    for cid in (a, b):
        w.add_history(cid, far1, precision="year")
        w.add_history(cid, far2, precision="year")
        w.review_target(cid)
    inp = w.build()
    pair = build_pairs(inp, [a, b])[(a, b)]
    assert pair.weight == 2.0 and pair.is_edge()


def test_one_shared_place_or_popular_places_is_not_an_edge():
    w = World()
    a, b = w.reviewer(), w.reviewer()
    far1 = w.place("Jaipur", "Dental clinic")
    fort, museum = w.place("Jaipur", "Fort"), w.place("Delhi NCR", "Museum")
    for cid in (a, b):
        for p in (far1, fort, museum):
            w.add_history(cid, p, precision="day", days_ago=30)
    inp = w.build()
    assert not edges(build_pairs(inp, [a, b]))


def test_timing_adds_weight():
    w = World()
    a, b = w.reviewer(), w.reviewer()
    near1, near2 = w.place("Pune", "Dental clinic", near_km=3), w.place("Pune", "Gym", near_km=3)
    for cid in (a, b):
        w.add_history(cid, near1, precision="day", days_ago=40)
        w.add_history(cid, near2, precision="day", days_ago=40)
    inp = w.build()
    pair = build_pairs(inp, [a, b])[(a, b)]
    assert pair.weight > 0.4  # each shared place gets (1 + c) with c = 1.0 when both are day-precise


def test_priority_ring_members_first_and_round_selection():
    w = World()
    ordinary = ordinary_reviewers(w, 30)
    ring = plant_ring(w, 8, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    inp = w.build()
    feats = compute_text_features(inp)
    bursts = detect_bursts(inp.target_reviews)
    cands = score_reviews(inp.target_reviews, bursts, feats)
    sel = select_round1(cands, inp.target.place_key, 8, 2)
    assert len(set(sel.round1) & set(ring)) >= 6
    assert len(sel.baseline) == 2 and not set(sel.baseline) & set(sel.round1)
    assert set(sel.baseline) <= set(ordinary) | set(ring)
    again = select_round1(cands, inp.target.place_key, 8, 2)
    assert again == sel  # fixed seed
    r2 = select_round2(sel, inp.target_reviews, feats, 15)
    assert len(r2) == 15 and not set(r2) & (set(sel.round1) | set(sel.baseline))


def test_small_business_expands_everyone():
    w = World()
    people = ordinary_reviewers(w, 7)
    inp = w.build()
    feats = compute_text_features(inp)
    cands = score_reviews(inp.target_reviews, detect_bursts(inp.target_reviews), feats)
    sel = select_round1(cands, "x", 8, 2)
    assert sorted(sel.round1) == sorted(people) and sel.baseline == [] and sel.remaining == []


def test_unknown_values_score_zero():
    r = TargetReview("x", "c", 3, T0, text="A long enough review text that is not short at all, really.")
    feats = compute_text_features(
        World()
        .build()
        .__class__(
            target=Place("t"),
            target_reviews=[r],
            places={},
            contributors={},
            histories={},
            expansions=[],
            fetched_at=T0,
        )
    )
    [c] = score_reviews([r], detect_bursts([r]), feats)
    assert c.score == 0

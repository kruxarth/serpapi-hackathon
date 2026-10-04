"""Evaluation harness (spec 10). Zero searches, no LLM, fixed seeds.

    uv run reviewring evaluate            # writes docs/evaluation/

Bases are cached clean analyses (the user's controls in data/cases.toml) when
they exist, otherwise synthetic clean businesses. Synthetic rings are planted
into each base, collection is simulated (priority score, round 1, early stop,
round 2) on the combined data, and the engine is run on what would have been
fetched. Recall is split by where each missed account was lost.
"""

from __future__ import annotations

import copy
import json
import math
import random
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import ALGORITHM_VERSION, config, db
from .engine.analyze import analyze
from .engine.features import compute_text_features
from .engine.graph import build_pairs, distance_km, edges, is_popular_type
from .engine.priority import score_reviews, select_round1, select_round2
from .engine.target_signals import detect_bursts
from .model import AnalysisInput, Contributor, Expansion, HistoryReview, Place, TargetReview
from .serp.catalog import FIRST_PAGE_SIZE, PAGE_SIZE
from .synth import CITIES, CLIENT_TYPES, TRAVEL_TYPES, World, jitter, ordinary_reviewers

OUT_DIR = config.REPO_ROOT / "docs" / "evaluation"
FLAGGED = {"ring", "possible_ring_trip"}
TEMPLATES = [
    "Very good service, highly recommended!",
    "Best experience, staff very helpful and polite.",
    "Excellent work, very professional team, thank you.",
    "Nice place and good service, must visit.",
    "Superb service at a reasonable price, 5 stars.",
]
TIMINGS = {  # name -> (days spread for the batch, precision label)
    "same day": (1, "day"),
    "same week": (6, "week"),
    "month": (30, "month"),
    "unknown": (60, "year"),
}
CAMOUFLAGE = {"none": 0, "low": 3, "high": 15}


# ---------------------------------------------------------------------- helpers


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def review_pages(n_reviews: int) -> int:
    return 1 + math.ceil(max(0, n_reviews - FIRST_PAGE_SIZE) / PAGE_SIZE)


def _date_range(fetch_day, days_ago: int, precision: str):
    width = {"day": 1, "week": 7, "month": 30, "year": 365}[precision]
    start = (days_ago // width) * width
    hi = fetch_day - timedelta(days=start)
    return hi - timedelta(days=width), hi


def _edit(rng: random.Random, text: str) -> str:
    words = text.split()
    if rng.random() < 0.6 and len(words) > 2:
        i = rng.randrange(len(words))
        words[i] = words[i].rstrip("!.,") + rng.choice(["", "!", "."])
    return " ".join(words)


# ---------------------------------------------------------------------- simulated collection


@dataclass
class SimResult:
    report: dict[str, Any]
    round1: list[str]
    baseline: list[str]
    round2: list[str]
    early_stop: bool
    searches: int


def simulate(
    full: AnalysisInput, *, k1: int, b: int, k2: int, cap_histories: int | None = None, no_early_stop: bool = False
) -> SimResult:
    """Run the collection logic on a world where every history is known, then the engine on what it fetched."""
    target_only = copy.copy(full)
    target_only.histories = {}
    target_only.text_features = None
    features = compute_text_features(target_only)
    cands = score_reviews(full.target_reviews, detect_bursts(full.target_reviews), features)
    sel = select_round1(cands, full.target.place_key, k1, b)
    r1 = sel.round1 + sel.baseline
    order = list(r1)
    probe = _restrict(full, [Expansion(c, 1, "priority") for c in r1])
    found = edges(build_pairs(probe, [c for c in r1 if probe.contributors[c].status == "ok"]))
    early = not found and not no_early_stop
    r2: list[str] = []
    if not early:
        r2 = select_round2(sel, full.target_reviews, features, k2)
        order += r2
    if cap_histories is not None:
        order = order[:cap_histories]
    expansions = [Expansion(c, 1 if c in r1 else 2, "baseline" if c in sel.baseline else "priority") for c in order]
    inp = _restrict(full, expansions)
    report = analyze(inp)
    return SimResult(
        report,
        sel.round1,
        sel.baseline,
        [c for c in r2 if c in order],
        early,
        review_pages(len(full.target_reviews)) + len(order),
    )


def _restrict(full: AnalysisInput, expansions: list[Expansion]) -> AnalysisInput:
    keep = {e.contributor_id for e in expansions}
    contributors = {}
    for cid in keep:
        c = full.contributors.get(cid)
        if c is None or cid not in full.histories:
            contributors[cid] = Contributor(cid, status="missing")
        else:
            contributors[cid] = c
    return AnalysisInput(
        target=full.target,
        target_reviews=full.target_reviews,
        places=full.places,
        contributors=contributors,
        histories={c: full.histories[c] for c in keep if c in full.histories},
        expansions=expansions,
        fetched_at=full.fetched_at,
        params=dict(full.params),
        text_features=None,
    )


# ---------------------------------------------------------------------- injection


def far_places(base: AnalysisInput, rng: random.Random, m: int, *, regional: bool = False) -> list[Place]:
    """m client places far from the target in >= 2 areas: real cached places first, invented ones as needed."""
    t = base.target
    pool = []
    if not regional:
        for p in base.places.values():
            d = distance_km(t, p)
            if d is not None and d > 50 and p.area and p.area != t.area and not is_popular_type(p.type):
                pool.append(p)
    pool.sort(key=lambda p: p.place_key)
    rng.shuffle(pool)
    chosen: list[Place] = []
    areas: set[str] = set()
    for p in pool:  # spread over areas first
        if len(chosen) < m and p.area not in areas:
            chosen.append(p)
            areas.add(p.area or "")
    for p in pool:
        if len(chosen) < m and p not in chosen:
            chosen.append(p)
    if regional:
        near = sorted(CITIES, key=lambda c: _km(t, c))
        cities = [c for c in near if 50 < _km(t, c) < 450][:3] or near[1:4]
        types = TRAVEL_TYPES[:3] + ["Guest house"]
    else:
        cities = [c for c in CITIES if t.lat is None or _km(t, c) > 300]
        types = CLIENT_TYPES
    i = 0
    while len(chosen) < m or len({p.area for p in chosen}) < 2:
        city = cities[i % len(cities)]
        lat, lng = jitter(rng, city)
        key = f"0xinj{rng.randrange(16**8):08x}:0x{i}"
        p = Place(key, key, f"Planted client {i}", None, lat, lng, types[i % len(types)], city)
        base.places[key] = p
        if len(chosen) >= m:
            chosen[-1] = p
        else:
            chosen.append(p)
        i += 1
    return chosen


def _km(t: Place, city: str) -> float:
    from .normalize.geo import haversine_km

    lat, lng = CITIES[city]
    return haversine_km(t.lat or 20.0, t.lng or 78.0, lat, lng)


def inject(
    base: AnalysisInput,
    *,
    k: int,
    m: int,
    camouflage: str,
    timing: str,
    seed: int,
    regional: bool = False,
    stealth: bool = False,
) -> tuple[AnalysisInput, list[str]]:
    """Plant k ring accounts. ``stealth`` makes them look aged: many reviews, photos, unique texts, mixed ratings."""
    rng = random.Random(seed)
    inp = copy.deepcopy(base)
    inp.text_features = None
    clients = far_places(inp, rng, m, regional=regional)
    filler_pool = sorted(
        {h.place_key for hs in base.histories.values() for h in hs if h.place_key} - {base.target.place_key}
    )
    spread, precision = TIMINGS[timing]
    fetch_day = inp.fetched_at.date()
    start = rng.randint(10, 60)
    members = []
    for i in range(k):
        cid = f"inj{seed}-{i}"
        n_filler = CAMOUFLAGE[camouflage]
        inp.contributors[cid] = Contributor(
            cid, None, None, None, None, {"reviews": m + n_filler + 1, "photos": 0}, 0, False, "ok", inp.fetched_at
        )
        hist: list[HistoryReview] = []
        template = rng.choice(TEMPLATES)
        for j, p in enumerate(clients):
            days = start + j * 20 + rng.randint(0, spread)
            lo, hi = _date_range(fetch_day, days, precision)
            hist.append(
                HistoryReview(
                    cid,
                    f"{cid}-c{j}",
                    p.place_key,
                    5 if rng.random() < 0.9 else 4,
                    None,
                    lo,
                    hi,
                    False,
                    [],
                    _edit(rng, template),
                )
            )
        for j in range(n_filler):
            key = rng.choice(filler_pool) if filler_pool else None
            if key is None:
                break
            lo, hi = _date_range(fetch_day, rng.randint(30, 700), "month")
            hist.append(
                HistoryReview(
                    cid,
                    f"{cid}-f{j}",
                    key,
                    rng.choice((3, 4, 5)),
                    None,
                    lo,
                    hi,
                    False,
                    [],
                    f"Filler review {j} with ordinary words number {rng.randint(0, 10**6)}",
                )
            )
        when = inp.fetched_at - timedelta(days=start - 5 + rng.uniform(0, spread))
        text = _edit(rng, template)
        rating = 5 if rng.random() < 0.9 else 4
        if stealth:
            from .synth import random_text

            text = random_text(rng)
            rating = rng.choice((5, 5, 4))
        lo, hi = _date_range(fetch_day, (inp.fetched_at - when).days, precision)
        hist.append(HistoryReview(cid, f"{cid}-t", inp.target.place_key, rating, None, lo, hi, False, [], text))
        inp.histories[cid] = hist
        inp.contributors[cid].reviews_returned = len(hist)
        inp.target_reviews.append(
            TargetReview(f"{cid}-r", cid, rating, when, False, text, False, m + n_filler + 1, 0, False)
        )
        members.append(cid)
    inp.target_reviews.sort(key=lambda r: r.posted_at or inp.fetched_at, reverse=True)
    return inp, members


def classify_losses(sim: SimResult, members: list[str]) -> dict[str, int]:
    labels = {r["contributor_id"]: r["label"] for r in sim.report["reviewers"]}
    groups = {m: g for g in sim.report["groups"] for m in g["members"]}
    out = {"caught": 0, "not_chosen": 0, "not_grouped": 0, "failed_rules": 0}
    for m in members:
        if m not in labels:
            out["not_chosen"] += 1
        elif labels[m] in FLAGGED:
            out["caught"] += 1
        elif m not in groups:
            out["not_grouped"] += 1
        else:
            out["failed_rules"] += 1
    return out


# ---------------------------------------------------------------------- bases


@dataclass
class Base:
    name: str
    input: AnalysisInput
    real: bool


def synthetic_bases(n: int = 3) -> list[Base]:
    out = []
    for i, (city, kind) in enumerate(
        [("Pune", "Dental clinic"), ("Bengaluru", "Restaurant"), ("Kolkata", "Coaching center"), ("Chennai", "Hotel")][
            :n
        ]
    ):
        w = World(target_city=city, target_type=kind, seed=1000 + i, total_reviews=800)
        ordinary_reviewers(w, 70, home=city, rating_pool=(5, 5, 4, 4, 3, 2, 1))
        inp = w.build()
        inp.expansions = []
        out.append(Base(f"synthetic-{i + 1} ({kind}, {city})", inp, False))
    return out


def load_cases() -> list[dict[str, Any]]:
    path = config.data_dir() / "cases.toml"
    if not path.exists():
        return []
    with path.open("rb") as f:
        return list(tomllib.load(f).get("case", []))


def real_input_for(url: str) -> tuple[str, AnalysisInput] | None:
    """Rebuild a cached analysis of this place (no network)."""
    from .collect import Collector, CollectParams
    from .resolve import parse_input
    from .serp.gateway import Gateway

    try:
        data_id = parse_input(url).data_id
    except Exception:  # noqa: BLE001 - a bad case line shouldn't stop the evaluation
        return None
    if not data_id:
        return None
    row = (
        db.connect()
        .execute(
            "SELECT id, input, params FROM analyses WHERE place_key = ? AND status = 'done' "
            "ORDER BY finished_at DESC LIMIT 1",
            (data_id,),
        )
        .fetchone()
    )
    if row is None:
        return None
    params = CollectParams(**json.loads(row["params"])) if row["params"] else CollectParams.from_config()
    out = Collector(Gateway(mode="offline"), row["input"], params, analysis_id=row["id"]).run()
    db.connect().execute("UPDATE analyses SET status = 'done' WHERE id = ?", (row["id"],))
    if out.status != "done" or out.input is None:
        return None
    return row["id"], out.input


# ---------------------------------------------------------------------- scenarios


def negative_scenarios(seed: int = 5, sizes: tuple[int, ...] = (3, 5, 8), repeats: int = 2) -> list[dict[str, Any]]:
    """Plant innocent group structures into ordinary reviewer populations, across group sizes.

    "Must not be flagged" scenarios pass only if no planted member is ever labelled ring, possible ring or
    suspicious. "Information only" scenarios are genuine coordination or known limits; their share is reported.
    """
    rows = []

    def member(w: World, home: str, *, ordinary: bool = True) -> str:
        cid = w.reviewer(total=60 if ordinary else 5, photos=20 if ordinary else 0)
        if ordinary:
            w.personal_history(cid, home, 20)
        return cid

    def visit(w: World, cid: str, places, ratings=(3, 4, 5), precision="week", days_ago=40):
        for p in places:
            w.add_history(cid, p, w.rng.choice(ratings), days_ago=days_ago, precision=precision)

    def trip(n, stops_spec, *, home="Pune", ordinary=True, ratings=(3, 4, 5), precision="week"):
        def build(w: World):
            stops = [w.place(c, t) for c, t in stops_spec]
            ids = []
            for _ in range(n):
                cid = member(w, home, ordinary=ordinary)
                visit(w, cid, stops, ratings, precision)
                w.review_target(cid, rating=5)
                ids.append(cid)
            return ids

        return build

    def hometown_friends(n):
        def build(w: World):
            shared = [w.place("Pune", t, near_km=6) for t in ("College", "Cafe", "Restaurant")]
            shared.append(w.place("Mumbai", "Dhaba"))  # an earlier trip together
            ids = []
            for _ in range(n):
                cid = member(w, "Pune")
                for p in shared:
                    w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=w.rng.randint(30, 600))
                w.review_target(cid, rating=5)
                ids.append(cid)
            return ids

        return build

    def local_circle(n):
        def build(w: World):
            spots = [w.place("Pune", t, near_km=3) for t in ("Cafe", "Restaurant", "Gym", "Bakery", "Bookstore")]
            ids = []
            for _ in range(n):
                cid = member(w, "Pune")
                for p in spots:
                    w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=w.rng.randint(5, 300), precision="day")
                w.review_target(cid, rating=5)
                ids.append(cid)
            return ids

        return build

    def family_support(n):
        """Relatives in several cities reviewing each other's shops: genuine coordination, not paid."""

        def build(w: World):
            homes = ["Delhi NCR", "Jaipur", "Lucknow", "Kolkata", "Indore", "Nagpur", "Chennai", "Kochi"]
            shops = [
                w.place(homes[i % len(homes)], t)
                for i, t in enumerate(("Clothing store", "Dentist", "Electronics store"))
            ]
            ids = []
            for i in range(n):
                cid = member(w, homes[i % len(homes)])
                visit(w, cid, shops, ratings=(5,), precision="month", days_ago=w.rng.randint(30, 300))
                w.review_target(cid, rating=5)
                ids.append(cid)
            return ids

        return build

    def wedding_friends(n):
        """Friends from several cities who met at two weddings in two cities: two episodes, never trip-like."""

        def build(w: World):
            homes = ["Delhi NCR", "Bengaluru", "Hyderabad", "Kolkata", "Chennai", "Indore", "Nagpur", "Lucknow"]
            first = [w.place("Jaipur", "Wedding venue"), w.place("Jaipur", "Hotel")]
            second = [w.place("Udaipur", "Wedding venue"), w.place("Udaipur", "Resort")]
            ids = []
            for i in range(n):
                cid = member(w, homes[i % len(homes)])
                visit(w, cid, first, days_ago=60)
                visit(w, cid, second, days_ago=200)
                w.review_target(cid, rating=5)
                ids.append(cid)
            return ids

        return build

    def colleagues(n):
        def build(w: World):
            hotels = [w.place(c, "Hotel") for c in ("Delhi NCR", "Bengaluru", "Hyderabad", "Kolkata")]
            ids = []
            for _ in range(n):
                cid = member(w, "Pune")
                for p in hotels:
                    h = w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=w.rng.randint(20, 400))
                    h.travel_group = "business"
                w.review_target(cid, rating=4)
                ids.append(cid)
            return ids

        return build

    scenarios = [
        (
            "Wedding party in one far city",
            True,
            "Pune",
            lambda n: trip(n, [("Jaipur", "Wedding venue"), ("Jaipur", "Hotel"), ("Jaipur", "Restaurant")]),
        ),
        (
            "Family trip",
            True,
            "Pune",
            lambda n: trip(n, [("Goa", "Resort"), ("Goa", "Restaurant"), ("Goa", "Beach"), ("Goa", "Cafe")]),
        ),
        (
            "Tour through two nearby states",
            True,
            "Pune",
            lambda n: trip(
                n,
                [
                    ("Udaipur", "Hotel"),
                    ("Udaipur", "Hindu temple"),
                    ("Udaipur", "Restaurant"),
                    ("Ahmedabad", "Hotel"),
                    ("Ahmedabad", "Cafe"),
                ],
                ratings=(2, 3, 4, 5),
            ),
        ),
        (
            "Package tour with the guide's emporium",
            True,
            "Pune",
            lambda n: trip(
                n, [("Jaipur", "Hotel"), ("Jaipur", "Fort"), ("Jodhpur", "Restaurant"), ("Jodhpur", "Handicraft store")]
            ),
        ),
        ("Hometown friends reviewing a far resort", True, "Goa", hometown_friends),
        ("Local circle of friends", True, "Pune", local_circle),
        (
            "Thin solicited tourists, all 5★ (expected: possible, trip-like)",
            False,
            "Pune",
            lambda n: trip(
                n,
                [("Jaipur", "Hotel"), ("Udaipur", "Resort"), ("Jodhpur", "Hotel")],
                ordinary=False,
                ratings=(5,),
                precision="month",
            ),
        ),
        ("Family support circle across cities (genuine coordination)", False, "Pune", family_support),
        ("Friends from several cities at two weddings", False, "Pune", wedding_friends),
        ("Colleagues at the same hotels in several cities (known limit)", False, "Pune", colleagues),
    ]
    for name, must_pass, city, factory in scenarios:
        row: dict[str, Any] = {"scenario": name, "kind": "must not be flagged" if must_pass else "information only"}
        worst = 0.0
        for n in sizes:
            shares = []
            for rep in range(repeats):
                w = World(
                    target_city=city,
                    target_type="Resort" if city == "Goa" else "Dental clinic",
                    seed=seed * 1000 + n * 10 + rep + len(rows) * 101,
                )
                ordinary_reviewers(w, 40, home=city)
                planted = factory(n)(w)
                sim = simulate(w.build(), k1=8, b=2, k2=15)
                labels = {r["contributor_id"]: r["label"] for r in sim.report["reviewers"]}
                flagged = [p for p in planted if labels.get(p) in FLAGGED or labels.get(p) == "suspicious"]
                shares.append(len(flagged) / len(planted))
            share = sum(shares) / len(shares)
            row[f"flagged (size {n})"] = round(share, 3)
            worst = max(worst, share)
        row["result"] = ("PASS" if worst == 0 else "FAIL") if must_pass else "-"
        rows.append(row)
    return rows


def trip_veto_ablation(seed: int = 9, repeats: int = 6) -> list[dict[str, Any]]:
    """Regional campaigns by aged accounts (4/5-star mix, one week, members in different cities): how many are
    hidden as "group trip" under the old rule (2 of 3 indicators) versus the evidence-based rule."""
    rows = []
    for requires in (False, True):
        hidden = shown = 0
        groups_cfg = config.load_tunables()["groups"]
        old = groups_cfg.get("trip_requires_positive_evidence", True)
        groups_cfg["trip_requires_positive_evidence"] = requires
        try:
            for rep in range(repeats):
                w = World(target_city="Jaipur", target_type="Hotel", seed=seed * 100 + rep)
                ordinary_reviewers(w, 40, home="Jaipur")
                hotels = [
                    w.place(c, t)
                    for c, t in (
                        ("Udaipur", "Hotel"),
                        ("Jodhpur", "Resort"),
                        ("Udaipur", "Restaurant"),
                        ("Jodhpur", "Hotel"),
                    )
                ]
                members = []
                for home in ["Kolkata", "Chennai", "Indore", "Nagpur", "Lucknow", "Kochi"]:
                    cid = w.reviewer(total=80, photos=30)
                    for p in hotels:
                        w.add_history(cid, p, w.rng.choice((4, 5)), days_ago=20, precision="week")
                    w.personal_history(cid, home, 25)
                    w.review_target(cid, rating=5)
                    members.append(cid)
                sim = simulate(w.build(), k1=8, b=2, k2=15)
                labels = {r["contributor_id"]: r["label"] for r in sim.report["reviewers"]}
                hidden += sum(1 for m in members if labels.get(m) == "group_trip")
                shown += sum(1 for m in members if labels.get(m) in FLAGGED)
        finally:
            groups_cfg["trip_requires_positive_evidence"] = old
        total = repeats * 6
        rows.append(
            {
                "trip rule": "evidence required (current)" if requires else "2 of 3 indicators (old)",
                "hidden as trip": round(hidden / total, 3),
                "shown as ring-like": round(shown / total, 3),
                "planted": total,
            }
        )
    return rows


# ---------------------------------------------------------------------- main


def run_evaluation(quick: bool = False, out_dir: Path | None = None) -> dict[str, Any]:
    cfg = config.load_tunables()["collection"]
    k1, b, k2 = cfg["k1"], cfg["baseline"], cfg["k2"]
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases()
    bases: list[Base] = []
    case_rows = []
    for case in cases:
        found = real_input_for(case.get("url", ""))
        if found is None:
            case_rows.append(
                {
                    "case": case.get("slug", "?"),
                    "role": case.get("role", "?"),
                    "expected": case.get("expected", "?"),
                    "actual": "not cached",
                }
            )
            continue
        _, inp = found
        report = analyze(inp)
        case_rows.append(
            {
                "case": case.get("slug") or case.get("role", "case"),
                "role": case.get("role", "?"),
                "expected": case.get("expected", "?"),
                "actual": report["level"]["level"],
                "match": report["level"]["level"] == case.get("expected"),
            }
        )
        if case.get("role") == "control":
            bases.append(Base(case.get("slug") or "control", inp, True))
    if not bases:
        bases = synthetic_bases(2 if quick else 3)

    # False positives on real (or synthetic ordinary) accounts, no injection.
    fp_flagged = fp_total = 0
    control_levels = []
    for base in bases:
        sim = simulate(base.input, k1=k1, b=b, k2=k2)
        control_levels.append(
            {
                "base": base.name,
                "level": sim.report["level"]["level"],
                "searches": sim.searches,
                "early_stop": sim.early_stop,
            }
        )
        for r in sim.report["reviewers"]:
            if r["status"] != "ok":
                continue
            fp_total += 1
            if r["label"] in FLAGGED or r["label"] == "suspicious":
                fp_flagged += 1
    lo, hi = wilson(fp_flagged, fp_total)

    ks = [3, 8, 20] if quick else [3, 5, 8, 12, 20]
    ms = [2, 4] if quick else [2, 4, 8]
    camos = ["none", "high"] if quick else list(CAMOUFLAGE)
    timings = ["same week", "unknown"] if quick else list(TIMINGS)
    grid_rows = []
    seed = 0
    for base in bases:
        for k in ks:
            for m in ms:
                for camo in camos:
                    for timing in timings:
                        seed += 1
                        inp, members = inject(base.input, k=k, m=m, camouflage=camo, timing=timing, seed=seed)
                        sim = simulate(inp, k1=k1, b=b, k2=k2)
                        losses = classify_losses(sim, members)
                        grid_rows.append(
                            {
                                "base": base.name,
                                "k": k,
                                "m": m,
                                "camouflage": camo,
                                "timing": timing,
                                **losses,
                                "planted": k,
                                "level": sim.report["level"]["level"],
                                "searches": sim.searches,
                            }
                        )

    regional_rows = []
    for base in bases:
        for k in (5, 8):
            seed += 1
            inp, members = inject(base.input, k=k, m=4, camouflage="none", timing="month", seed=seed, regional=True)
            sim = simulate(inp, k1=k1, b=b, k2=k2)
            labels = {r["contributor_id"]: r["label"] for r in sim.report["reviewers"]}
            regional_rows.append(
                {
                    "base": base.name,
                    "k": k,
                    "as_ring": sum(1 for m in members if labels.get(m) == "ring"),
                    "as_possible_trip": sum(1 for m in members if labels.get(m) == "possible_ring_trip"),
                    "planted": k,
                    "level": sim.report["level"]["level"],
                }
            )

    stealth_rows = []
    for base in bases:
        for k in (5, 8, 12):
            caught = {"caught": 0, "not_chosen": 0, "not_grouped": 0, "failed_rules": 0}
            for _ in range(2 if quick else 4):
                seed += 1
                inp, members = inject(base.input, k=k, m=4, camouflage="high", timing="month", seed=seed, stealth=True)
                for key, v in classify_losses(simulate(inp, k1=k1, b=b, k2=k2), members).items():
                    caught[key] += v
            n = k * (2 if quick else 4)
            stealth_rows.append(
                {
                    "base": base.name,
                    "k": k,
                    "recall": round(caught["caught"] / n, 3),
                    "not chosen": round(caught["not_chosen"] / n, 3),
                    "not grouped": round(caught["not_grouped"] / n, 3),
                    "failed rules": round(caught["failed_rules"] / n, 3),
                    "planted": n,
                }
            )

    curve = []
    budgets = [4, 6, 8, 10, 13, 16, 20, 25]
    for cap in budgets:
        caught = planted = 0
        searches = []
        for base in bases:
            for i in range(3 if quick else 6):
                inp, members = inject(base.input, k=8, m=4, camouflage="low", timing="same week", seed=50_000 + i)
                sim = simulate(inp, k1=k1, b=b, k2=k2, cap_histories=cap, no_early_stop=True)
                caught += classify_losses(sim, members)["caught"]
                planted += len(members)
                searches.append(sim.searches)
        curve.append(
            {
                "histories": cap,
                "searches": round(sum(searches) / len(searches), 1),
                "recall": round(caught / planted, 3),
            }
        )

    negatives = negative_scenarios(repeats=1 if quick else 2)
    ablation = trip_veto_ablation(repeats=3 if quick else 6)

    hard_planted = sum(r["planted"] for r in stealth_rows)
    hard_caught = round(sum(r["recall"] * r["planted"] for r in stealth_rows))
    total = defaultdict(int)
    for r in grid_rows:
        for key in ("caught", "not_chosen", "not_grouped", "failed_rules", "planted"):
            total[key] += r[key]
    by = lambda key: _group(grid_rows, key)  # noqa: E731
    detected = sum(1 for r in grid_rows if r["level"] in ("High", "Elevated"))
    results = {
        "algorithm_version": ALGORITHM_VERSION,
        "bases": [{"name": b_.name, "real": b_.real} for b_ in bases],
        "summary": {
            "Bases": ", ".join(b_.name for b_ in bases)
            + (" (real cached controls)" if bases[0].real else " (synthetic; no cached controls yet)"),
            "Recall on harder rings (aged accounts, photos, unique texts, spread timing)": (
                f"{hard_caught / hard_planted:.1%} ({hard_caught}/{hard_planted}); almost every loss is at the "
                "priority step"
            ),
            "Recall on rings shaped like our own model (optimistic)": (
                f"{total['caught'] / total['planted']:.1%} ({total['caught']}/{total['planted']})"
            ),
            "Lost: not chosen by the priority score": f"{total['not_chosen'] / total['planted']:.1%}",
            "Lost: chosen but not in any group": f"{total['not_grouped'] / total['planted']:.1%}",
            "Lost: grouped, but the group failed the ring rules": f"{total['failed_rules'] / total['planted']:.1%}",
            "Businesses with a planted ring rated High or Elevated": f"{detected / len(grid_rows):.1%}",
            "False-positive rate on unplanted accounts": f"{fp_flagged}/{fp_total} = "
            f"{(fp_flagged / fp_total if fp_total else 0):.1%} (95% Wilson interval {lo:.1%}–{hi:.1%}; "
            f"small sample)",
            "Negative scenarios passed": f"{sum(1 for r in negatives if r['result'] == 'PASS')}/"
            f"{sum(1 for r in negatives if r['result'] != '-')}",
        },
        "tables": [
            {"title": "Recall by ring size (k)", "rows": by("k")},
            {"title": "Recall by shared places (m)", "rows": by("m")},
            {"title": "Recall by camouflage", "rows": by("camouflage")},
            {"title": "Recall by timing", "rows": by("timing")},
            {"title": "Regional travel-only rings (within ~450 km)", "rows": regional_rows},
            {
                "title": "Harder rings: aged accounts, photos, unique texts, spread timing (information only)",
                "rows": stealth_rows,
            },
            {"title": "Negative scenarios (share of planted members flagged, by group size)", "rows": negatives},
            {"title": "Ablation: regional campaigns hidden by the trip rule", "rows": ablation},
            {"title": "Clean bases without planted rings", "rows": control_levels},
            {"title": "Credits vs recall (k=8, m=4, low camouflage, same week)", "rows": curve},
            {"title": "Real cases from data/cases.toml", "rows": case_rows} if case_rows else None,
        ],
        "grid": grid_rows,
        "curve": curve,
        "charts": [],
        "honesty": "Planted rings follow our own model of a ring, so recall on them is optimistic.",
    }
    results["tables"] = [t for t in results["tables"] if t]
    results["charts"] = make_charts(results, out_dir)
    (out_dir / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n")
    (out_dir / "results.md").write_text(to_markdown(results))
    return results


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    agg: dict[Any, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for f in ("caught", "not_chosen", "not_grouped", "failed_rules", "planted"):
            agg[r[key]][f] += r[f]
    order = list(dict.fromkeys(r[key] for r in rows))
    return [
        {
            key: v,
            "recall": round(agg[v]["caught"] / agg[v]["planted"], 3),
            "not chosen": round(agg[v]["not_chosen"] / agg[v]["planted"], 3),
            "not grouped": round(agg[v]["not_grouped"] / agg[v]["planted"], 3),
            "failed rules": round(agg[v]["failed_rules"] / agg[v]["planted"], 3),
            "planted": agg[v]["planted"],
        }
        for v in order
    ]


def to_markdown(results: dict[str, Any]) -> str:
    lines = [
        "# Evaluation results",
        "",
        f"Algorithm version {results['algorithm_version']}. "
        "Reproduce with `uv run reviewring evaluate` (fixed seeds, zero searches, no AI).",
        "",
        f"> {results['honesty']}",
        "",
    ]
    for k, v in results["summary"].items():
        lines.append(f"- **{k}:** {v}")
    for chart in results["charts"]:
        lines += ["", f"![{chart['title']}]({chart['file']})"]
    for t in results["tables"]:
        rows = t["rows"]
        if not rows:
            continue
        lines += ["", f"## {t['title']}", "", "| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
        lines += ["| " + " | ".join(str(v) for v in r.values()) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def make_charts(results: dict[str, Any], out_dir: Path) -> list[dict[str, str]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, secondary, muted, grid, surface = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
    blue = "#2a78d6"
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.edgecolor": grid,
            "axes.labelcolor": secondary,
            "xtick.color": muted,
            "ytick.color": muted,
            "figure.facecolor": surface,
            "axes.facecolor": surface,
        }
    )
    charts = []

    curve = results["curve"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=150)
    xs = [c["searches"] for c in curve]
    ys = [c["recall"] * 100 for c in curve]
    ax.plot(xs, ys, color=blue, linewidth=2, marker="o", markersize=5, markeredgecolor=surface, markeredgewidth=1.5)
    for x, y, c in zip(xs, ys, curve, strict=True):
        if c["histories"] in (8, 25):
            ax.annotate(
                f"{y:.0f}% at {x:.0f} searches",
                (x, y),
                textcoords="offset points",
                xytext=(6, -14),
                color=ink,
                fontsize=9,
            )
    ax.set_xlabel("Searches per analysis")
    ax.set_ylabel("Planted accounts caught (%)")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", color=grid, linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Credits vs recall", loc="left", color=ink, fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "credits_vs_recall.png")
    plt.close(fig)
    charts.append({"file": "credits_vs_recall.png", "title": "Credits vs recall"})

    by_k = next(t for t in results["tables"] if t["title"].startswith("Recall by ring size"))["rows"]
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=150)
    labels = [str(r["k"]) for r in by_k]
    parts = [
        ("recall", "Caught", blue),
        ("not chosen", "Not chosen", "#c3c2b7"),
        ("not grouped", "Not grouped", "#898781"),
        ("failed rules", "Failed ring rules", "#52514e"),
    ]
    bottom = [0.0] * len(by_k)
    for key, name, color in parts:
        vals = [r[key] * 100 for r in by_k]
        ax.bar(labels, vals, bottom=bottom, color=color, label=name, width=0.6, edgecolor=surface, linewidth=2)
        bottom = [b_ + v for b_, v in zip(bottom, vals, strict=True)]
    ax.set_xlabel("Planted ring size (accounts)")
    ax.set_ylabel("Share of planted accounts (%)")
    ax.set_ylim(0, 100)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    ax.set_title("Where planted accounts were caught or lost", loc="left", color=ink, fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "recall_by_k.png")
    plt.close(fig)
    charts.append({"file": "recall_by_k.png", "title": "Where planted accounts were caught or lost"})
    return charts

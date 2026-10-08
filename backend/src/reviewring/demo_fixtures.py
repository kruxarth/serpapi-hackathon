"""Synthetic demo fixtures: invented worlds run through the real pipeline and exporter.

They let demo mode work on a fresh clone before any real data exists, and they
are labelled "synthetic" everywhere they appear.
"""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path

from . import config
from . import demo_texts as T
from .collect import Collector
from .exporter import build_fixture, write_fixture
from .fake_serp import FakeSerpApi
from .leakcheck import originals_from_cache
from .llm import valid_cues, voice_items
from .model import AnalysisInput
from .serp.gateway import Gateway
from .synth import CLIENT_TYPES, FETCHED, World, ordinary_reviewers, plant_ring

URL = "https://www.google.com/maps/place/T/data=!4m2!3m1!1s0x5eed:0x1"
SALT = "synthetic-demo"


def ring_world() -> World:
    w = World(target_city="Pune", target_type="Dental clinic", total_reviews=640, rating=4.4, seed=101)
    ordinary_reviewers(w, 70, rating_pool=(5, 5, 5, 4, 4, 4, 3, 2))
    plant_ring(
        w,
        12,
        cities=["Jaipur", "Kochi", "Lucknow", "Kolkata"],
        m=6,
        timing="week",
        camouflage=3,
        template="Best clinic in the city, very caring doctor and staff, highly recommended!!",
    )
    return w


def trip_world() -> World:
    """A resort whose recent reviews include a family trip: ruled out, level stays Low."""
    w = World(target_city="Udaipur", target_type="Resort", total_reviews=2300, rating=4.2, seed=202)
    ordinary_reviewers(w, 70, home="Udaipur", rating_pool=(5, 5, 4, 4, 4, 3))
    stops = [
        w.place("Jaipur", "Hotel"),
        w.place("Jaipur", "Hindu temple"),
        w.place("Jodhpur", "Restaurant"),
        w.place("Jodhpur", "Hotel"),
        w.place("Udaipur", "Cafe"),
    ]
    when = FETCHED - timedelta(days=12)
    for i in range(8):
        cid = w.reviewer(total=w.rng.randint(30, 90), photos=w.rng.randint(5, 50))
        for p in stops:
            w.add_history(cid, p, w.rng.choice((3, 4, 5)), days_ago=14, precision="week")
        w.personal_history(cid, "Mumbai", 25)  # a family shares one home
        w.review_target(cid, rating=5, when=when + timedelta(hours=i * 3))
    return w


def regional_world() -> World:
    """A hotel whose reviewers only ever review hotels in one region, all 5 stars: possible ring (trip-like)."""
    w = World(target_city="Jaipur", target_type="Hotel", total_reviews=900, rating=4.1, seed=303)
    ordinary_reviewers(w, 70, home="Jaipur", rating_pool=(5, 4, 4, 4, 3))
    hotels = [
        w.place(c, t)
        for c, t in (("Udaipur", "Hotel"), ("Jodhpur", "Resort"), ("Udaipur", "Guest house"), ("Jodhpur", "Hotel"))
    ]
    for _ in range(6):
        cid = w.reviewer(total=w.rng.randint(4, 8), photos=0)
        for p in hotels:
            w.add_history(cid, p, 5, precision="month", days_ago=w.rng.randint(40, 200))
        w.review_target(cid, rating=5, when=FETCHED - timedelta(days=w.rng.uniform(5, 60)))
    return w


def movers_world() -> World:
    """The most common real pattern: a burst of 5-star reviews from first-time accounts, plus polished
    AI-style texts, one pasted chatbot reply and a template copied across accounts."""
    w = World(target_city="Bengaluru", target_type="Packers and movers", total_reviews=410, rating=4.9, seed=404)
    ordinary_reviewers(w, 50, home="Bengaluru", rating_pool=(5, 5, 5, 5, 4, 4, 3, 1))
    burst_day = FETCHED - timedelta(days=58)
    for i in range(26):
        cid = w.reviewer(total=1, photos=0)
        text = T.MOVERS_TEMPLATE if i % 5 == 0 else T.MOVERS_BURST_SHORT[i % len(T.MOVERS_BURST_SHORT)]
        if i % 5 == 0 and i:
            text = text.replace("Highly recommended!", "Highly recommend.") if i % 2 else text.lower()
        w.review_target(cid, rating=5, when=burst_day + timedelta(hours=i * 1.8), text=text)
    for i, (text, _) in enumerate(T.MOVERS_AI):
        cid = w.reviewer(total=w.rng.randint(1, 3), photos=0)
        w.review_target(cid, rating=5, when=FETCHED - timedelta(days=8 + i * 13, hours=i), text=text)
    cid = w.reviewer(total=64, photos=120, level=6)
    w.personal_history(cid, "Bengaluru", 30)
    w.review_target(cid, rating=4, when=FETCHED - timedelta(days=27), text=T.MOVERS_POLISHED[0])
    for i, (text, rating) in enumerate(T.MOVERS_HUMAN):
        cid = w.reviewer(total=w.rng.randint(6, 60), photos=w.rng.randint(0, 30))
        w.personal_history(cid, "Bengaluru", w.rng.randint(5, 15))
        w.review_target(cid, rating=rating, when=FETCHED - timedelta(days=5 + i * 17), text=text)
    cid = w.reviewer(total=1, photos=0)
    w.review_target(cid, rating=5, when=FETCHED - timedelta(days=63), text=T.MOVERS_CHATBOT)
    for _ in range(9):  # real customers who made an account just to review: context, not a warning sign
        cid = w.reviewer(total=1, photos=w.rng.choice((0, 0, 2)))
        w.review_target(cid, rating=w.rng.choice((5, 5, 4, 3)))
    return w


def hotel_world() -> World:
    """A rating carried by old reviews: shows 4.8, the newest 100 average about 3.2, and the highest-rated reviews
    are an old batch from first-time accounts. Plus a pasted chatbot reply, AI-style texts and a reviewing spree."""
    w = World(target_city="Delhi NCR", target_type="Hotel", total_reviews=5200, rating=4.8, seed=505)
    ordinary_reviewers(w, 85, home="Delhi NCR", rating_pool=(1, 2, 2, 3, 3, 3, 4, 4, 4, 5))
    when = FETCHED - timedelta(days=19)
    for i, (text, _) in enumerate(T.HOTEL_AI):
        cid = w.reviewer(total=w.rng.randint(1, 2), photos=0)
        w.review_target(cid, rating=5, when=when + timedelta(hours=5 * i), text=text)
    for i, (text, rating) in enumerate(T.HOTEL_HUMAN):
        cid = w.reviewer(total=w.rng.randint(8, 70), photos=w.rng.randint(0, 40))
        w.personal_history(cid, w.rng.choice(("Mumbai", "Pune", "Lucknow", "Jaipur")), w.rng.randint(6, 18))
        w.review_target(cid, rating=rating, when=FETCHED - timedelta(days=3 + i * 21), text=text)
    cid = w.reviewer(total=1, photos=0)
    w.review_target(cid, rating=5, when=FETCHED - timedelta(days=44), text=T.HOTEL_CHATBOT)
    # A "rate hotels and earn" worker: a dozen hotels in six cities within a month, all 5 stars.
    spree = w.reviewer(total=14, photos=0)
    for j, city in enumerate(["Mumbai", "Jaipur", "Goa", "Kochi", "Hyderabad", "Kolkata"] * 2):
        w.add_history(
            spree,
            w.place(city, "Hotel" if j % 3 else CLIENT_TYPES[j % len(CLIENT_TYPES)]),
            5,
            days_ago=20 + j * 2,
            precision="week",
            text="Good",
        )
    w.review_target(spree, rating=5, when=when + timedelta(hours=2), text="Nice hotel")
    for _ in range(6):
        cid = w.reviewer(total=1, photos=0)
        w.review_target(cid, rating=w.rng.choice((4, 3, 2, 5)))
    for i in range(33):  # the old batch the displayed rating rests on
        cid = w.reviewer(total=1, photos=0)
        w.review_target(
            cid,
            rating=5,
            when=FETCHED - timedelta(days=420 + i * 2, hours=i),
            text=T.HOTEL_OLD_BATCH[i % len(T.HOTEL_OLD_BATCH)],
        )
    return w


def scripted_world() -> World:
    """Scripted reviews from real-looking aged accounts: written like search ads, and not in the reviewers' own voice.
    The pattern every account-based check misses (docs/research-2026-10-08.md)."""
    w = World(target_city="Pune", target_type="Packers and movers", total_reviews=1800, rating=4.6, seed=606)
    w.target.title = "Shubh Yatra Movers"  # its reviews spell out "Shubh Yatra Packers and Movers"
    w.target.address = "Shop 12, Kothrud, Pune, Maharashtra"
    ordinary_reviewers(w, 52, home="Pune", rating_pool=(5, 5, 4, 4, 3, 1))
    for i in range(len(T.SCRIPTED)):
        text, _, own = T.SCRIPTED[i]
        cid = w.reviewer(total=w.rng.randint(3, 40), photos=w.rng.randint(0, 6))
        for j, t in enumerate(own):
            w.add_history(
                cid,
                w.place("Pune", ("Restaurant", "Corporate office", "Hardware store")[j % 3]),
                5,
                days_ago=w.rng.randint(300, 2500),
                precision="year",
                text=t,
            )
        w.review_target(cid, rating=5, when=FETCHED - timedelta(days=3 + i * 3, hours=i), text=text)
    return w


AI_CUES = {text: cues for text, cues in [*T.MOVERS_AI, T.MOVERS_POLISHED, *T.HOTEL_AI]}
SCRIPTED = {text: (here, own) for text, here, own in T.SCRIPTED}


def synthetic_judgements(inp: AnalysisInput) -> dict[str, dict]:
    """The AI-text opinion for invented texts, written with them (demo mode never calls a model)."""
    min_words = int(config.tunable("ai_text", "min_words"))
    out = {}
    for r in inp.target_reviews:
        if not r.text or len(r.text.split()) < min_words:
            continue
        cues = AI_CUES.get(r.text)
        if cues and len(valid_cues(cues, r.text)) != len(cues):
            raise ValueError(f"cues not found in their own text: {cues}")
        out[r.review_id] = {
            "verdict": "ai_style" if cues else "human_style",
            "cues": cues or [],
            "model": "synthetic example",
        }
    return out


def synthetic_voices(inp: AnalysisInput) -> dict[str, dict]:
    """The voice comparison for invented texts, written with them (demo mode never calls a model). Covers exactly the
    reviewers the real job would compare."""
    out = {}
    for item in voice_items(inp):
        scripted = SCRIPTED.get(item["here"])
        out[item["contributor_id"]] = (
            {
                "verdict": "different_voice",
                "here": scripted[0],
                "elsewhere": scripted[1][0],
                "model": "synthetic example",
            }
            if scripted
            else {"verdict": "same_voice", "here": "", "elsewhere": "", "model": "synthetic example"}
        )
    return out


CASES = [
    ("synthetic-movers", "Synthetic example: movers with a burst of first-time accounts", movers_world),
    ("synthetic-hotel", "Synthetic example: hotel whose rating is carried by old reviews", hotel_world),
    (
        "synthetic-scripted",
        "Synthetic example: movers with scripted reviews from real-looking accounts",
        scripted_world,
    ),
    ("synthetic-ring", "Synthetic example: dental clinic with a country-wide ring", ring_world),
    ("synthetic-trip", "Synthetic example: resort with a family trip (ruled out)", trip_world),
    ("synthetic-regional", "Synthetic example: hotel with a regional possible ring", regional_world),
]


def make_all(directory: Path | None = None) -> list[Path]:
    paths = []
    old = os.environ.get("REVIEWRING_DATA_DIR")
    try:
        for slug, title, build in CASES:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["REVIEWRING_DATA_DIR"] = tmp
                config.load_tunables.cache_clear()
                world = build()
                gw = Gateway(
                    secrets=config.Secrets("fakekey-not-real-demo", None),
                    client=FakeSerpApi(world),
                    sleep=lambda s: None,
                )
                out = Collector(gw, URL).run()
                if out.status != "done" or out.input is None:
                    raise RuntimeError(f"{slug}: collection ended with {out.status}: {out.message}")
                out.input.text_judgements = synthetic_judgements(out.input)
                out.input.voice_judgements = synthetic_voices(out.input)
                fixture = build_fixture(out.input, slug, title=title, synthetic=True, salt_value=SALT)
                paths.append(write_fixture(fixture, originals=originals_from_cache(), directory=directory))
    finally:
        if old is None:
            os.environ.pop("REVIEWRING_DATA_DIR", None)
        else:
            os.environ["REVIEWRING_DATA_DIR"] = old
        config.load_tunables.cache_clear()
    return paths

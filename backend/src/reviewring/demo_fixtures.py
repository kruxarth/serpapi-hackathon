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
from .collect import Collector
from .exporter import build_fixture, write_fixture
from .fake_serp import FakeSerpApi
from .leakcheck import originals_from_cache
from .serp.gateway import Gateway
from .synth import FETCHED, World, ordinary_reviewers, plant_ring

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
        w.personal_history(cid, w.rng.choice(["Mumbai", "Ahmedabad"]), 25)
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


CASES = [
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
                fixture = build_fixture(out.input, slug, title=title, synthetic=True, salt_value=SALT)
                paths.append(write_fixture(fixture, originals=originals_from_cache(), directory=directory))
    finally:
        if old is None:
            os.environ.pop("REVIEWRING_DATA_DIR", None)
        else:
            os.environ["REVIEWRING_DATA_DIR"] = old
        config.load_tunables.cache_clear()
    return paths

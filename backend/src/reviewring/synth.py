"""Synthetic analyses for tests, the evaluation harness and the demo.

Everything here is invented: place names, reviewers and texts. City centre
coordinates are public geography, not personal data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from .model import AnalysisInput, Contributor, Expansion, HistoryReview, Place, TargetReview

CITIES: dict[str, tuple[float, float]] = {
    "Pune": (18.5204, 73.8567),
    "Mumbai": (19.0760, 72.8777),
    "Delhi NCR": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462),
    "Kochi": (9.9312, 76.2673),
    "Ahmedabad": (23.0225, 72.5714),
    "Indore": (22.7196, 75.8577),
    "Goa": (15.4909, 73.8278),
    "Udaipur": (24.5854, 73.7125),
    "Jodhpur": (26.2389, 73.0243),
    "Nagpur": (21.1458, 79.0882),
}

PERSONAL_TYPES = [
    "Restaurant",
    "Cafe",
    "Grocery store",
    "Pharmacy",
    "Hair salon",
    "Gym",
    "Bakery",
    "Clothing store",
    "Electronics store",
    "Dentist",
    "Hospital",
    "Bookstore",
]
CLIENT_TYPES = [
    "Dental clinic",
    "Hair transplantation clinic",
    "Packers and movers",
    "Coaching center",
    "Hotel",
    "IVF clinic",
    "Skin care clinic",
    "Interior designer",
    "Car dealer",
    "Resort",
]
TRAVEL_TYPES = ["Hotel", "Restaurant", "Resort", "Tourist attraction", "Hindu temple", "Cafe", "Guest house"]

_OPENERS = [
    "Went here",
    "Visited",
    "Stopped by",
    "We came",
    "I tried this place",
    "Came with family",
    "Dropped in",
    "Our second visit",
    "First time here",
    "Booked in advance",
]
_WHEN = [
    "last weekend",
    "on a weekday",
    "after work",
    "during the holidays",
    "for a birthday",
    "in the morning",
    "late evening",
    "on a rainy day",
    "with friends",
    "before a flight",
]
_OPINIONS = [
    "the staff were polite but slow",
    "prices felt a little high",
    "parking was a real problem",
    "quality was consistent with before",
    "the waiting time was long",
    "everything was neat and clean",
    "service could be better",
    "it was crowded but manageable",
    "they fixed our issue quickly",
    "the menu had fewer options now",
    "value for money is decent",
    "the location is easy to find",
]
_ENDINGS = [
    "Would come again.",
    "Not sure I will return.",
    "Okay overall.",
    "Mixed feelings.",
    "Decent enough.",
    "Recommended for families.",
    "Average experience.",
    "Might try once more.",
]


def random_text(rng: random.Random) -> str:
    """A varied, invented review sentence (so unrelated reviews don't look like near-duplicates)."""
    parts = [rng.choice(_OPENERS), rng.choice(_WHEN) + ",", rng.choice(_OPINIONS)]
    if rng.random() < 0.6:
        parts.append("and " + rng.choice(_OPINIONS) + ".")
    else:
        parts[-1] += "."
    parts.append(rng.choice(_ENDINGS))
    return " ".join(parts)


FETCHED = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
FETCH_DAY = date(2026, 9, 28)


def jitter(rng: random.Random, city: str, km: float = 8.0) -> tuple[float, float]:
    lat, lng = CITIES[city]
    d = km / 111.0
    return round(lat + rng.uniform(-d, d), 5), round(lng + rng.uniform(-d, d), 5)


@dataclass
class World:
    """Builder for an AnalysisInput with named places, reviewers and histories."""

    target_city: str = "Pune"
    target_type: str = "Dental clinic"
    total_reviews: int | None = 900
    rating: float | None = 4.7
    seed: int = 7
    rng: random.Random = field(init=False)
    places: dict[str, Place] = field(default_factory=dict)
    target_reviews: list[TargetReview] = field(default_factory=list)
    contributors: dict[str, Contributor] = field(default_factory=dict)
    histories: dict[str, list[HistoryReview]] = field(default_factory=dict)
    expansions: list[Expansion] = field(default_factory=list)
    _n: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        lat, lng = CITIES[self.target_city]
        self.target = Place(
            "0x5eed:0x1",
            "0x5eed:0x1",
            "Target business",
            None,
            lat,
            lng,
            self.target_type,
            self.target_city,
            self.rating,
            self.total_reviews,
        )
        self.places[self.target.place_key] = self.target

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n:05d}"

    def place(self, city: str, type_: str, *, near_km: float = 8.0, key: str | None = None) -> Place:
        key = key or f"0x{self._next('p')}:0x1"
        lat, lng = jitter(self.rng, city, near_km)
        p = Place(key, key, f"Invented {type_} {key[2:8]}", None, lat, lng, type_, city)
        self.places[key] = p
        return p

    def reviewer(
        self,
        *,
        total: int | None = 40,
        photos: int | None = 10,
        level: int | None = None,
        cid: str | None = None,
    ) -> str:
        cid = cid or self._next("u")
        self.contributors[cid] = Contributor(
            cid,
            None,
            level,
            None,
            None,
            {"reviews": total, "photos": photos} if total is not None else {},
            0,
            False,
            "ok",
            FETCHED,
        )
        self.histories[cid] = []
        return cid

    def review_target(
        self,
        cid: str | None,
        *,
        rating: int = 5,
        when: datetime | None = None,
        text: str | None = None,
        total: int | None = None,
        photos: int | None = None,
    ) -> TargetReview:
        rid = self._next("r")
        when = when or FETCHED - timedelta(days=self.rng.uniform(0, 120))
        c = self.contributors.get(cid) if cid else None
        r = TargetReview(
            rid,
            cid,
            rating,
            when,
            False,
            text if text is not None else random_text(self.rng),
            False,
            total if total is not None else (c.total_reviews if c else None),
            photos if photos is not None else (c.total_photos if c else None),
            None,
        )
        self.target_reviews.append(r)
        if cid:
            self.add_history(cid, self.target, rating, days_ago=(FETCHED - when).days, precision="week", text=r.text)
        return r

    def add_history(
        self,
        cid: str,
        place: Place,
        rating: int = 5,
        *,
        days_ago: int | None = None,
        precision: str = "month",
        text: str | None = None,
    ) -> HistoryReview:
        """precision: day | week | month | year | unknown."""
        days_ago = days_ago if days_ago is not None else self.rng.randint(10, 700)
        width = {"day": 1, "week": 7, "month": 30, "year": 365}.get(precision)
        if width is None:
            lo = hi = None
        else:
            start = (days_ago // width) * width
            hi = FETCH_DAY - timedelta(days=start)
            lo = hi - timedelta(days=width)
        h = HistoryReview(
            cid,
            self._next("h"),
            place.place_key,
            rating,
            None,
            lo,
            hi,
            False,
            [],
            text if text is not None else f"Invented review {self._n} of a place.",
        )
        self.histories.setdefault(cid, []).append(h)
        c = self.contributors.get(cid)
        if c:
            c.reviews_returned = len(self.histories[cid])
        return h

    def personal_history(self, cid: str, city: str, n: int, *, ratings=(3, 4, 5, 5, 4, 2)) -> None:
        for _ in range(n):
            p = self.place(city, self.rng.choice(PERSONAL_TYPES))
            self.add_history(cid, p, self.rng.choice(ratings))

    def expand(self, cid: str, round_: int = 1, reason: str = "priority") -> None:
        if all(e.contributor_id != cid for e in self.expansions):
            self.expansions.append(Expansion(cid, round_, reason))

    def build(self) -> AnalysisInput:
        for cid in self.contributors:
            if cid in self.histories and any(h.place_key == self.target.place_key for h in self.histories[cid]):
                self.expand(cid)
        return AnalysisInput(
            target=self.target,
            target_reviews=sorted(self.target_reviews, key=lambda r: r.posted_at or FETCHED, reverse=True),
            places=self.places,
            contributors=self.contributors,
            histories=self.histories,
            expansions=self.expansions,
            fetched_at=FETCHED,
        )


def ordinary_reviewers(world: World, n: int, *, home: str | None = None, rating_pool=(3, 4, 5, 5, 2, 1)) -> list[str]:
    """Real-looking reviewers: histories of personal places around home, varied ratings."""
    out = []
    for _ in range(n):
        cid = world.reviewer(total=world.rng.randint(15, 120), photos=world.rng.randint(0, 60))
        world.personal_history(cid, home or world.target_city, world.rng.randint(10, 30))
        world.review_target(cid, rating=world.rng.choice(rating_pool))
        out.append(cid)
    return out


def plant_ring(
    world: World,
    k: int,
    *,
    cities: list[str],
    m: int = 4,
    types: list[str] | None = None,
    camouflage: int = 0,
    timing: str = "week",
    thin: bool = True,
    template: str = "Very good service, highly recommended, best in the city!",
    base_days_ago: int = 20,
) -> list[str]:
    """k accounts reviewing the target plus m shared client places in the given cities."""
    types = types or CLIENT_TYPES
    clients = [world.place(cities[i % len(cities)], types[i % len(types)]) for i in range(m)]
    members = []
    for _i in range(k):
        cid = world.reviewer(
            total=world.rng.randint(3, 6) if thin else world.rng.randint(30, 80),
            photos=0 if thin else world.rng.randint(5, 40),
        )
        for j, client in enumerate(clients):
            days = base_days_ago + j * 25 + (0 if timing in ("day", "week") else world.rng.randint(0, 30))
            world.add_history(
                cid,
                client,
                5,
                days_ago=days,
                precision=timing if timing != "spread" else "month",
                text=_edit(world.rng, template),
            )
        for _ in range(camouflage):
            world.add_history(
                cid,
                world.place(world.rng.choice(list(CITIES)), world.rng.choice(PERSONAL_TYPES)),
                world.rng.choice((4, 5)),
            )
        when = FETCHED - timedelta(days=base_days_ago - 5, hours=world.rng.uniform(0, 48))
        world.review_target(cid, rating=5, when=when, text=_edit(world.rng, template))
        members.append(cid)
    return members


def _edit(rng: random.Random, template: str) -> str:
    words = template.split()
    if len(words) > 3 and rng.random() < 0.5:
        i = rng.randrange(len(words))
        words[i] = words[i].rstrip("!.,") + rng.choice(["", ".", "!!"])
    return " ".join(words)

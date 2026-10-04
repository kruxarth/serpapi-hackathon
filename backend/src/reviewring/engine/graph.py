"""Place surprise weights, pair weights and edges (spec 9.4, 9.5).

Why not Adamic-Adar: it down-weights places many sampled reviewers share, but
within our sample the places a ring shares are exactly the most shared ones.
Distance from the target and place type stand in for global popularity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .. import config
from ..model import AnalysisInput, HistoryReview, Place
from ..normalize.geo import haversine_km
from .homes import Home, compute_homes


def is_popular_type(place_type: str | None) -> bool:
    """Popular when the type's last word is on the list, unless the whole type is excluded."""
    if not place_type:
        return False
    cfg = config.load_tunables()["surprise"]
    text = " ".join(place_type.casefold().split())
    if text in {e.casefold() for e in cfg["popular_exclusions"]}:
        return False
    last = text.split(" ")[-1] if text else ""
    return last in {w.casefold() for w in cfg["popular_last_words"]}


def distance_km(target: Place, place: Place) -> float | None:
    if None in (target.lat, target.lng, place.lat, place.lng):
        return None
    return haversine_km(target.lat, target.lng, place.lat, place.lng)  # type: ignore[arg-type]


def surprise(target: Place, place: Place, homes: tuple[Home | None, ...] = ()) -> float:
    """Distance factor x type factor. Distance is to the business or to either reviewer's home, whichever is nearer."""
    cfg = config.load_tunables()["surprise"]
    d = distance_km(target, place)
    if place.lat is not None and place.lng is not None:
        for home in homes:
            if home is not None:
                dh = haversine_km(home.lat, home.lng, place.lat, place.lng)
                d = dh if d is None else min(d, dh)
    if d is None:
        dist = cfg["no_coords_factor"]
    elif d < cfg["near_km"]:
        dist = cfg["near_factor"]
    elif d <= cfg["mid_km"]:
        dist = cfg["mid_factor"]
    else:
        dist = cfg["far_factor"]
    kind = cfg["popular_factor"] if is_popular_type(place.type) else cfg["other_factor"]
    return float(dist) * float(kind)


def coincidence(a: HistoryReview, b: HistoryReview) -> float:
    """c: how closely two reviews of the same place coincide in time. Only ever adds weight."""
    pa, pb = a.precision_days, b.precision_days
    if pa is None or pb is None:
        return 0.0
    if not (a.date_min <= b.date_max and b.date_min <= a.date_max):  # type: ignore[operator]
        return 0.0
    worst = max(pa, pb)
    for max_days, c in config.tunable("edges", "timing"):
        if worst <= max_days:
            return float(c)
    return 0.0


@dataclass
class SharedPlace:
    place_key: str
    surprise: float
    coincidence: float
    popular: bool

    @property
    def weight(self) -> float:
        return self.surprise * (1 + self.coincidence)


@dataclass
class Pair:
    u: str
    v: str
    shared: list[SharedPlace] = field(default_factory=list)

    @property
    def weight(self) -> float:
        return sum(s.weight for s in self.shared)

    @property
    def non_popular(self) -> int:
        return sum(1 for s in self.shared if not s.popular)

    def is_edge(self) -> bool:
        return self.weight >= float(config.tunable("edges", "min_weight")) and self.non_popular >= int(
            config.tunable("edges", "min_non_popular_shared")
        )


def reviews_by_place(inp: AnalysisInput, contributors: list[str]) -> dict[str, dict[str, list[HistoryReview]]]:
    """place_key -> contributor -> their reviews of it, excluding the target itself."""
    out: dict[str, dict[str, list[HistoryReview]]] = {}
    for cid in contributors:
        for h in inp.histories.get(cid, []):
            if not h.place_key or h.place_key == inp.target.place_key:
                continue
            out.setdefault(h.place_key, {}).setdefault(cid, []).append(h)
    return out


def build_pairs(
    inp: AnalysisInput, contributors: list[str], homes: dict[str, Home] | None = None
) -> dict[tuple[str, str], Pair]:
    """Every pair of the given reviewers that shares at least one place."""
    contributors = sorted(set(contributors))
    if homes is None:
        homes = compute_homes(inp, contributors)
    index = reviews_by_place(inp, contributors)
    pairs: dict[tuple[str, str], Pair] = {}
    for place_key in sorted(index):
        who = index[place_key]
        if len(who) < 2:
            continue
        place = inp.places.get(place_key) or Place(place_key)
        popular = is_popular_type(place.type)
        for u, v in combinations(sorted(who), 2):
            s = surprise(inp.target, place, (homes.get(u), homes.get(v)))
            c = max(coincidence(a, b) for a in who[u] for b in who[v])
            pairs.setdefault((u, v), Pair(u, v)).shared.append(SharedPlace(place_key, s, c, popular))
    return pairs


def edges(pairs: dict[tuple[str, str], Pair]) -> dict[tuple[str, str], Pair]:
    return {k: p for k, p in pairs.items() if p.is_edge()}

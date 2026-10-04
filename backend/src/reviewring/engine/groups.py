"""Groups, trip-like shapes, rings and confidence (spec 9.6)."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations
from typing import Any

import networkx as nx

from .. import config
from ..model import AnalysisInput, HistoryReview
from ..normalize.geo import haversine_km
from .accounts import CONTEXT_ONLY, AccountSignals
from .graph import Pair, coincidence, distance_km, is_popular_type
from .homes import Home


@lru_cache(maxsize=1)
def _type_group_patterns() -> list[tuple[str, bool, re.Pattern[str]]]:
    out = []
    for g in config.load_tunables()["type_groups"]:
        words = "|".join(re.escape(k.casefold()) for k in sorted(g["keywords"], key=len, reverse=True))
        out.append((g["name"], bool(g["travel"]), re.compile(rf"(?<!\w)(?:{words})(?!\w)")))
    return out


def type_group(place_type: str | None) -> tuple[str, bool]:
    """(group name, is a travel group). Unmatched types are "Other", not travel."""
    text = (place_type or "").casefold()
    for name, travel, pattern in _type_group_patterns():
        if pattern.search(text):
            return name, travel
    return "Other", False


@dataclass
class Group:
    group_id: str
    members: list[str]
    pruned: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    trip: dict[str, Any] = field(default_factory=dict)
    verdict: str = "none"  # ring | possible_ring | possible_ring_trip | ruled_out_trip | social_circle | none
    confidence: float | None = None
    confidence_parts: list[dict[str, Any]] = field(default_factory=list)
    core_places: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "members": self.members,
            "pruned": self.pruned,
            "edges": [list(e) for e in self.edges],
            "metrics": self.metrics,
            "trip": self.trip,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "confidence_parts": self.confidence_parts,
            "core_places": self.core_places,
        }


def _density(g: nx.Graph) -> float:
    n = g.number_of_nodes()
    return 0.0 if n < 2 else g.number_of_edges() / (n * (n - 1) / 2)


def find_components(edge_pairs: dict[tuple[str, str], Pair]) -> list[list[str]]:
    """Connected components; large loose ones are split with Louvain (fixed seed)."""
    cfg = config.load_tunables()["groups"]
    g = nx.Graph()
    for (u, v), p in edge_pairs.items():
        g.add_edge(u, v, weight=p.weight)
    out: list[list[str]] = []
    for comp in sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: c[0]):
        sub = g.subgraph(comp)
        if len(comp) >= cfg["louvain_min_size"] and _density(sub) < cfg["louvain_max_density"]:
            parts = nx.community.louvain_communities(
                sub, weight="weight", seed=int(config.tunable("collection", "seed"))
            )
            out.extend(sorted(sorted(p) for p in parts))
        else:
            out.append(comp)
    return out


def prune(members: list[str], edge_pairs: dict[tuple[str, str], Pair]) -> tuple[list[str], list[str]]:
    """Remove hangers-on: members with fewer than max(2, ceil(30% of the others)) edges inside the group."""
    cfg = config.load_tunables()["groups"]
    keep = sorted(members)
    removed: list[str] = []
    while True:
        need = max(cfg["prune_min_edges"], math.ceil(cfg["prune_share"] * (len(keep) - 1)))
        degree = {m: 0 for m in keep}
        for u, v in combinations(keep, 2):
            if (u, v) in edge_pairs:
                degree[u] += 1
                degree[v] += 1
        weak = sorted(m for m in keep if degree[m] < need)
        if not weak:
            return keep, removed
        # Remove the weakest first, one at a time, so a removal can't cascade unfairly.
        victim = min(weak, key=lambda m: (degree[m], m))
        keep.remove(victim)
        removed.append(victim)
        if not keep:
            return keep, removed


def _episodes(dates: list[tuple[Any, Any]], gap_days: int) -> int:
    dates = sorted(dates)
    count = 0
    end = None
    for lo, hi in dates:
        if end is None or (lo - end).days > gap_days:
            count += 1
            end = hi
        else:
            end = max(end, hi)
    return count


def group_metrics(
    inp: AnalysisInput, members: list[str], signals: dict[str, AccountSignals], homes: dict[str, Home] | None = None
) -> tuple[dict[str, Any], list[str]]:
    cfg = config.load_tunables()["groups"]
    n = len(members)
    target_key = inp.target.place_key
    by_place: dict[str, dict[str, list[HistoryReview]]] = {}
    for cid in members:
        for h in inp.histories.get(cid, []):
            if h.place_key and h.place_key != target_key:
                by_place.setdefault(h.place_key, {}).setdefault(cid, []).append(h)

    need = max(cfg["core_min_members"], math.ceil(cfg["core_share"] * n))
    core = sorted(
        k
        for k, who in by_place.items()
        if len(who) >= need and not is_popular_type((inp.places.get(k) or _blank(k)).type)
    )
    core_places = [inp.places.get(k) or _blank(k) for k in core]

    far = set()
    for p in core_places:
        d = distance_km(inp.target, p)
        if d is not None and d > cfg["far_km"] and p.area and p.area != inp.target.area:
            far.add(p.area)
    located = [p for p in core_places if p.lat is not None]
    span = max((haversine_km(a.lat, a.lng, b.lat, b.lng) for a, b in combinations(located, 2)), default=0.0)
    groups_seen = sorted({type_group(p.type)[0] for p in core_places})
    travel_share = sum(1 for p in core_places if type_group(p.type)[1]) / len(core_places) if core_places else 0.0

    core_reviews = [(k, cid, h) for k in core for cid, hs in by_place[k].items() for h in hs]
    precise = [
        h
        for _, _, h in core_reviews
        if h.precision_days is not None and h.precision_days <= cfg["episode_precision_days"]
    ]
    timing_known = bool(core_reviews) and len(precise) * 2 >= len(core_reviews)
    episodes = _episodes([(h.date_min, h.date_max) for h in precise], cfg["episode_gap_days"]) if timing_known else None

    co_timed = 0
    for k, cid, h in core_reviews:
        others = [o for other, hs in by_place[k].items() if other != cid for o in hs]
        if any(coincidence(h, o) > 0 for o in others):
            co_timed += 1
    co_timing = co_timed / len(core_reviews) if (core_reviews and timing_known) else None

    shared_keys = {k for k, who in by_place.items() if len(who) >= 2}
    shares = []
    for cid in members:
        visible = [h for h in inp.histories.get(cid, []) if h.place_key and h.place_key != target_key]
        if visible:
            shares.append(sum(1 for h in visible if h.place_key in shared_keys) / len(visible))
    concentration = statistics.median(shares) if shares else 0.0

    rated = [h.rating for _, _, h in core_reviews if h.rating is not None]
    five_share = sum(1 for r in rated if r == 5) / len(rated) if rated else None
    # Home areas: do most members share one, and do the core places sit near it?
    homes = homes or {}
    member_homes = [homes[m] for m in members if m in homes]
    home_area, home_members, near_home = None, 0, 0.0
    if member_homes:
        home_area, home_members = min(
            ((a, sum(1 for h in member_homes if h.area == a)) for a in {h.area for h in member_homes}),
            key=lambda x: (-x[1], x[0]),
        )
        anchor = [h for h in member_homes if h.area == home_area]
        lat = sum(h.lat for h in anchor) / len(anchor)
        lng = sum(h.lng for h in anchor) / len(anchor)
        if located:
            near_home = sum(1 for p in located if haversine_km(lat, lng, p.lat, p.lng) <= cfg["social_km"]) / len(
                core_places
            )
    trip_groups = {g.casefold() for g in cfg["trip_travel_groups"]}
    with_party = sum(
        1
        for cid in members
        if any((h.travel_group or "") in trip_groups for k in core for h in by_place[k].get(cid, []))
    )
    with_signals = sum(
        1
        for cid in members
        if cid in signals
        and signals[cid].count(exclude=CONTEXT_ONLY) >= config.tunable("confidence", "member_signals_min")
    )
    return (
        {
            "size": n,
            "core_places": len(core),
            "core_min_members": need,
            "far_areas": sorted(far),
            "far_area_count": len(far),
            "span_km": round(span, 1),
            "type_groups": groups_seen,
            "type_diversity": len(groups_seen),
            "core_travel_share": round(travel_share, 3),
            "core_non_travel": sum(1 for p in core_places if not type_group(p.type)[1]),
            "home_area": home_area,
            "home_member_share": round(home_members / n, 3) if n else 0.0,
            "core_near_home_share": round(near_home, 3),
            "travel_party_share": round(with_party / n, 3) if n else 0.0,
            "episodes": episodes,
            "timing_known": timing_known,
            "concentration": round(concentration, 3),
            "core_five_star_share": None if five_share is None else round(five_share, 3),
            "co_timing_ratio": None if co_timing is None else round(co_timing, 3),
            "member_signal_share": round(with_signals / n, 3) if n else 0.0,
        },
        core,
    )


def _blank(key: str):
    from ..model import Place

    return Place(key)


def is_social_circle(m: dict[str, Any]) -> bool:
    """Most members share a home area and most core places are near it: friends or family, not clients."""
    cfg = config.load_tunables()["groups"]
    return (
        m["home_area"] is not None
        and m["home_member_share"] >= cfg["social_min_member_share"]
        and m["core_near_home_share"] >= cfg["social_min_core_share"]
    )


def trip_assessment(m: dict[str, Any]) -> dict[str, Any]:
    """A trip is ruled out only on positive evidence (a shared home, or hotel reviews saying family/friends),
    never merely because farm signs are absent. Otherwise trip evidence caps a group at "possible"."""
    cfg = config.load_tunables()["groups"]
    # Mostly travel businesses: at least 75% of core places, or all but one when there are 3 or more
    # (a tour guide's emporium or a pharmacy shouldn't break the shape).
    mostly_travel = m["core_travel_share"] >= cfg["trip_min_travel_share"] or (
        m["core_places"] >= 3 and m["core_non_travel"] <= 1
    )
    shape = (
        m["span_km"] <= cfg["trip_max_span_km"]
        and mostly_travel
        and not (m["episodes"] is not None and m["episodes"] >= 2)
    )
    indicators = {
        "one_episode": m["episodes"] == 1,
        "low_concentration": m["concentration"] < cfg["trip_concentration_below"],
        "varied_ratings": m["core_five_star_share"] is not None
        and m["core_five_star_share"] < cfg["trip_five_star_share_below"],
    }
    met = sum(indicators.values())
    evidence = {
        "shared_home": m["home_member_share"] >= cfg["social_min_member_share"],
        "travel_party": m["travel_party_share"] >= cfg["social_min_member_share"],
    }
    if not shape:
        status = "no_trip_shape"
    elif met >= cfg["trip_indicators_needed"] and (
        any(evidence.values()) or not cfg.get("trip_requires_positive_evidence", True)
    ):
        status = "ruled_out"
    else:
        status = "unresolved"
    return {
        "trip_like_shape": shape,
        "indicators": indicators,
        "indicators_met": met,
        "positive_evidence": evidence,
        "status": status,
    }


def confidence(m: dict[str, Any], density: float) -> tuple[float, list[dict[str, Any]]]:
    w = config.load_tunables()["confidence"]
    parts = [
        ("Density", density, w["density"]),
        ("Core places", min(m["core_places"] / w["core_places_full"], 1.0), w["core_places"]),
        ("Dispersion", min(m["far_area_count"] / w["far_areas_full"], 1.0), w["dispersion"]),
        ("Type diversity", min(m["type_diversity"] / w["type_groups_full"], 1.0), w["type_diversity"]),
        ("Concentration", min(m["concentration"] / w["concentration_full"], 1.0), w["concentration"]),
        ("Timing", m["co_timing_ratio"], w["timing"]),
        ("Member signals", m["member_signal_share"], w["member_signals"]),
    ]
    used = [(name, v, wt) for name, v, wt in parts if v is not None]
    total_w = sum(wt for _, _, wt in used)
    score = sum(v * wt for _, v, wt in used) / total_w if total_w else 0.0
    out = [
        {"part": name, "value": None if v is None else round(v, 3), "weight": wt, "used": v is not None}
        for name, v, wt in parts
    ]
    return round(score, 3), out


def detect_groups(
    inp: AnalysisInput,
    edge_pairs: dict[tuple[str, str], Pair],
    signals: dict[str, AccountSignals],
    homes: dict[str, Home] | None = None,
) -> list[Group]:
    cfg = config.load_tunables()["groups"]
    groups: list[Group] = []
    for comp in find_components(edge_pairs):
        members, pruned = prune(comp, edge_pairs)
        if len(members) < 2:
            continue
        g = nx.Graph()
        g.add_nodes_from(members)
        group_edges = [(u, v) for u, v in combinations(members, 2) if (u, v) in edge_pairs]
        g.add_edges_from(group_edges)
        density = _density(g)
        metrics, core = group_metrics(inp, members, signals, homes)
        metrics["density"] = round(density, 3)
        trip = trip_assessment(metrics)
        structural = (
            density >= cfg["ring_min_density"]
            and metrics["core_places"] >= cfg["ring_min_core_places"]
            and metrics["far_area_count"] >= cfg["ring_min_far_areas"]
        )
        n = len(members)
        substantive = n >= cfg["possible_ring_min_size"] and metrics["core_places"] >= 2
        if is_social_circle(metrics):
            verdict = "social_circle" if substantive else "none"
        elif trip["status"] == "ruled_out":
            verdict = "ruled_out_trip" if substantive else "none"
        elif trip["status"] == "unresolved":
            verdict = "possible_ring_trip" if structural and n >= cfg["possible_ring_min_size"] else "none"
        elif structural and n >= cfg["ring_min_size"]:
            verdict = "ring"
        elif structural and n >= cfg["possible_ring_min_size"]:
            verdict = "possible_ring"
        else:
            verdict = "none"
        group = Group(f"G{len(groups) + 1}", members, pruned, group_edges, metrics, trip, verdict, core_places=core)
        if verdict in ("ring", "possible_ring", "possible_ring_trip"):
            group.confidence, group.confidence_parts = confidence(metrics, density)
        groups.append(group)
    order = {"ring": 0, "possible_ring": 1, "possible_ring_trip": 2, "ruled_out_trip": 3, "social_circle": 4, "none": 5}
    groups.sort(key=lambda g: (order[g.verdict], -(g.confidence or 0), -len(g.members), g.members[0]))
    for i, g in enumerate(groups):
        g.group_id = f"G{i + 1}"
    return groups

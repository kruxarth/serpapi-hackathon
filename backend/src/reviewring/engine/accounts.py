"""Account signals A1-A8 (spec 9.7). Percentages use the visible history only."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from .. import config
from ..model import AnalysisInput, HistoryReview, TargetReview
from ..normalize.geo import haversine_km
from ..normalize.text import TextFeatures
from .features import history_text_id, target_text_id
from .graph import is_popular_type
from .target_signals import BurstResult

CONTEXT_ONLY = {"A3", "A4", "A8", "A9"}
SIGNAL_NAMES = {
    "A1": "Thin profile",
    "A2": "Rating monotony",
    "A3": "Several cities in one week",
    "A4": "Same-day distant reviews",
    "A5": "Short texts",
    "A6": "Copy-paste text",
    "A7": "Burst participant",
    "A8": "Reworded template (AI)",
    "A9": "Reviewing spree",
}


@dataclass
class AccountSignals:
    contributor_id: str
    badges: dict[str, dict[str, Any]] = field(default_factory=dict)  # code -> details

    def has(self, code: str) -> bool:
        return code in self.badges

    def count(self, exclude: set[str] | None = None) -> int:
        return sum(1 for c in self.badges if c not in (exclude or set()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "contributor_id": self.contributor_id,
            "badges": [{"code": c, "name": SIGNAL_NAMES[c], **d} for c, d in sorted(self.badges.items())],
        }


def _dated(h: HistoryReview, max_precision: int) -> bool:
    p = h.precision_days
    return p is not None and p <= max_precision


def compute_signals(
    inp: AnalysisInput,
    features: dict[str, TextFeatures],
    bursts: BurstResult,
    stock_clusters: set[str],
    paraphrase_groups: dict[str, int] | None = None,
) -> dict[str, AccountSignals]:
    """Badges for every expanded reviewer. ``paraphrase_groups`` maps target review_id -> group (A8)."""
    cfg = config.load_tunables()["signals"]
    target_by_owner: dict[str, list[TargetReview]] = defaultdict(list)
    for r in inp.target_reviews:
        if r.contributor_id:
            target_by_owner[r.contributor_id].append(r)
    cluster_members: dict[str, set[str]] = defaultdict(set)
    for f in features.values():
        if f.cluster:
            cluster_members[f.cluster].add(f.owner or f"anon:{f.text_id}")
    paraphrase_owners: dict[int, set[str]] = defaultdict(set)
    for r in inp.target_reviews:
        g = (paraphrase_groups or {}).get(r.review_id)
        if g is not None and r.contributor_id:
            paraphrase_owners[g].add(r.contributor_id)

    out: dict[str, AccountSignals] = {}
    for exp in inp.expansions:
        cid = exp.contributor_id
        c = inp.contributors.get(cid)
        sig = AccountSignals(cid)
        out[cid] = sig
        mine = target_by_owner.get(cid, [])
        history = inp.histories.get(cid, [])

        # A1 thin profile. Level counts only when present.
        total = c.total_reviews if c else None
        photos = c.total_photos if c else None
        if total is None and mine:
            total = mine[0].reviewer_reviews
        if photos is None and mine:
            photos = mine[0].reviewer_photos
        level = c.level if c else None
        thin = total is not None and total <= cfg["thin_max_reviews"] and photos == 0
        if thin or (level is not None and level <= cfg["thin_max_level"]):
            sig.badges["A1"] = {"total_reviews": total, "photos": photos, "level": level}

        # A2 rating monotony.
        rated = [h.rating for h in history if h.rating is not None]
        if len(rated) >= cfg["monotony_min_reviews"]:
            share = sum(1 for x in rated if x == 5) / len(rated)
            if share >= cfg["monotony_share"]:
                sig.badges["A2"] = {"five_star_share": round(share, 3), "visible_reviews": len(rated)}

        located = [(h, inp.places.get(h.place_key)) for h in history if h.place_key and inp.places.get(h.place_key)]
        # A3 several cities in one week (context only).
        week = [(h, p) for h, p in located if _dated(h, cfg["multi_city_days"]) and p.lat is not None]
        week.sort(key=lambda hp: (hp[0].date_min, hp[0].review_id))
        for i, (h, _) in enumerate(week):
            window = [(x, p) for x, p in week[i:] if (x.date_min - h.date_min).days <= cfg["multi_city_days"]]
            areas = {p.area for _, p in window if p.area}
            if len(areas) < cfg["multi_city_min_areas"]:
                continue
            spread = max(
                (haversine_km(a.lat, a.lng, b.lat, b.lng) for (_, a), (_, b) in combinations(window, 2)), default=0
            )
            if spread >= cfg["multi_city_min_km"]:
                sig.badges["A3"] = {"areas": sorted(areas), "from": h.date_min.isoformat(), "km": round(spread)}
                break

        # A4 same-day distant reviews (context only; never "impossible").
        day = [(h, p) for h, p in located if _dated(h, 1) and p.lat is not None]
        occasions: dict[str, dict[str, Any]] = {}
        for (a, pa), (b, pb) in combinations(day, 2):
            if not (a.date_min <= b.date_max and b.date_min <= a.date_max):
                continue
            km = haversine_km(pa.lat, pa.lng, pb.lat, pb.lng)
            if km >= cfg["same_day_min_km"]:
                key = max(a.date_min, b.date_min).isoformat()
                occasions.setdefault(key, {"day": key, "places": [pa.place_key, pb.place_key], "km": round(km)})
        if len(occasions) >= cfg["same_day_min_occasions"]:
            sig.badges["A4"] = {"occasions": [occasions[k] for k in sorted(occasions)]}

        # A5 short texts, over the target review and the visible history.
        text_ids = [target_text_id(r.review_id) for r in mine]
        text_ids += [history_text_id(cid, h.review_id) for h in history if h.place_key != inp.target.place_key]
        feats = [features[t] for t in text_ids if t in features]
        if feats:
            share = sum(1 for f in feats if f.short) / len(feats)
            if share >= cfg["short_text_share"]:
                sig.badges["A5"] = {"short_share": round(share, 3), "texts": len(feats)}

        # A6 copy-paste: their target review is a near-duplicate of another reviewer's text.
        for r in mine:
            f = features.get(target_text_id(r.review_id))
            if f and f.cluster and f.cluster not in stock_clusters and len(cluster_members[f.cluster] - {cid}) >= 1:
                sig.badges["A6"] = {"cluster": f.cluster, "accounts": len(cluster_members[f.cluster])}
                break

        # A7 burst participant.
        for r in mine:
            b = bursts.burst_for(r)
            if b is not None:
                sig.badges["A7"] = {"burst_start": b.start.isoformat(), "burst_end": b.end.isoformat()}
                break

        # A8 reworded template (optional, from the DeepSeek paraphrase signal; context only).
        for r in mine:
            g = (paraphrase_groups or {}).get(r.review_id)
            if g is not None and len(paraphrase_owners[g] - {cid}) >= 1:
                sig.badges["A8"] = {"group": g}
                break

        # A9 reviewing spree (context only): many unrelated businesses in several cities within a month, ~all 5-star.
        spree = reviewing_spree(inp, history)
        if spree:
            sig.badges["A9"] = spree
    return out


def reviewing_spree(inp: AnalysisInput, history: list[HistoryReview]) -> dict[str, Any] | None:
    """The busiest window of ``window_days`` among non-popular places, if it has enough reviews, areas and 5-stars.

    The shape of "rate hotels and earn" tasks: one account rating many unrelated businesses across cities in a few
    weeks, nearly all 5-star. Some travellers review this way too, so it's context, never counted.
    """
    cfg = config.load_tunables()["spree"]
    dated = []
    for h in history:
        place = inp.places.get(h.place_key) if h.place_key else None
        if place is None or h.place_key == inp.target.place_key or is_popular_type(place.type):
            continue
        if not _dated(h, cfg["max_precision_days"]):
            continue
        mid = h.date_min + (h.date_max - h.date_min) / 2  # type: ignore[operator]
        dated.append((mid, h, place))
    dated.sort(key=lambda x: (x[0], x[1].review_id))
    best: list = []
    for i, (start, _, _) in enumerate(dated):
        window = [x for x in dated[i:] if (x[0] - start).days <= cfg["window_days"]]
        if len({h.place_key for _, h, _ in window}) > len({h.place_key for _, h, _ in best}):
            best = window
    places = {h.place_key for _, h, _ in best}
    areas = {p.area for _, _, p in best if p.area}
    rated = [h.rating for _, h, _ in best if h.rating is not None]
    if len(places) < cfg["min_reviews"] or len(areas) < cfg["min_areas"] or not rated:
        return None
    five = sum(1 for x in rated if x == 5) / len(rated)
    if five < cfg["min_five_star_share"]:
        return None
    return {
        "places": len(places),
        "areas": sorted(areas),
        "from": best[0][0].isoformat(),
        "to": best[-1][0].isoformat(),
        "five_star_share": round(five, 3),
    }

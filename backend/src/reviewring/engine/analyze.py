"""Run the whole engine on an AnalysisInput and produce the report (spec 9.6-9.12).

Deterministic: same input and tunables, same report. Wording follows Rule 6:
"suspicious", "coordinated", "ring-like pattern"; never a verdict on a business
or a person.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

from .. import ALGORITHM_VERSION, config
from ..model import AnalysisInput
from ..normalize.dates import ist_date
from ..normalize.text import cluster_owners
from .accounts import compute_signals
from .features import compute_text_features, target_text_id
from .graph import build_pairs, distance_km, edges, is_popular_type, surprise
from .groups import Group, detect_groups, type_group
from .target_signals import (
    detect_bursts,
    rating_histogram,
    target_duplicate_clusters,
    thin_profile_skew,
    young_business,
)

LABELS = ["ring", "possible_ring_trip", "suspicious", "group_trip", "no_flags", "not_checked"]
LABEL_TEXT = {
    "ring": "Ring",
    "possible_ring_trip": "Possible ring (trip-like)",
    "suspicious": "Suspicious",
    "group_trip": "Group trip",
    "no_flags": "No flags",
    "not_checked": "Not checked",
}


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _list_words(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def stock_phrase_clusters(inp: AnalysisInput, features, edge_pairs) -> set[str]:
    """Clusters used by >= N accounts of which < 20% have an edge to another account using it."""
    cfg = config.load_tunables()["text"]
    owners = cluster_owners(features.values())
    out = set()
    for cluster, accounts in owners.items():
        if len(accounts) < cfg["stock_phrase_min_accounts"]:
            continue
        connected = sum(1 for a in accounts if any(tuple(sorted((a, b))) in edge_pairs for b in accounts if b != a))
        if connected / len(accounts) < cfg["stock_phrase_max_connected_share"]:
            out.add(cluster)
    return out


def analyze(inp: AnalysisInput, paraphrase_groups: dict[str, int] | None = None) -> dict[str, Any]:
    features = compute_text_features(inp)
    bursts = detect_bursts(inp.target_reviews)
    expanded = [e.contributor_id for e in inp.expansions]
    usable = [c for c in expanded if inp.contributors.get(c) and inp.contributors[c].status == "ok"]
    all_pairs = build_pairs(inp, usable)
    edge_pairs = edges(all_pairs)
    stock = stock_phrase_clusters(inp, features, edge_pairs)
    signals = compute_signals(inp, features, bursts, stock, paraphrase_groups)
    groups = detect_groups(inp, edge_pairs, signals)

    # ---------------------------------------------------------------- labels
    membership: dict[str, Group] = {}
    for g in groups:
        for m in g.members:
            membership.setdefault(m, g)
    reviewer_label: dict[str, str] = {}
    for cid in expanded:
        c = inp.contributors.get(cid)
        g = membership.get(cid)
        if c is None or c.status in ("missing", "error"):
            reviewer_label[cid] = "not_checked"
        elif g is not None and g.verdict in ("ring", "possible_ring"):
            reviewer_label[cid] = "ring"
        elif g is not None and g.verdict == "possible_ring_trip":
            reviewer_label[cid] = "possible_ring_trip"
        elif signals[cid].has("A6") and signals[cid].count(exclude={"A6"}) >= 2:
            reviewer_label[cid] = "suspicious"
        elif g is not None and g.verdict == "ruled_out_trip":
            reviewer_label[cid] = "group_trip"
        else:
            reviewer_label[cid] = "no_flags"

    review_rows = []
    for r in inp.target_reviews:
        label = reviewer_label.get(r.contributor_id or "", "not_checked")
        f = features.get(target_text_id(r.review_id))
        review_rows.append(
            {
                "review_id": r.review_id,
                "contributor_id": r.contributor_id,
                "rating": r.rating,
                "date": r.posted_at.isoformat() if r.posted_at else None,
                "day": ist_date(r.posted_at).isoformat() if r.posted_at else None,
                "label": label,
                "badges": sorted(signals[r.contributor_id].badges) if r.contributor_id in signals else [],
                "text": r.text,
                "text_length": f.length if f else None,
                "script": f.script if f else None,
                "cluster": f.cluster if f and f.cluster not in stock else None,
                "stock_phrase": bool(f and f.cluster in stock),
                "short": bool(f and f.short),
                "reviewer_reviews": r.reviewer_reviews,
                "local_guide": r.local_guide,
            }
        )
    label_counts = Counter(row["label"] for row in review_rows)
    examined = len(review_rows)

    # ---------------------------------------------------------------- ratings
    def mean(rows) -> float | None:
        vals = [row["rating"] for row in rows if row["rating"] is not None]
        return round(statistics.fmean(vals), 2) if vals else None

    ring_rows = [row for row in review_rows if row["label"] == "ring"]
    sample_mean = mean(review_rows)
    without_ring = mean([row for row in review_rows if row["label"] != "ring"])
    strict = mean([row for row in review_rows if row["label"] not in ("ring", "suspicious", "possible_ring_trip")])
    overall = None
    displayed, total = inp.target.rating, inp.target.total_reviews
    if displayed is not None and total and ring_rows and total > len(ring_rows):
        ring_sum = sum(row["rating"] or 0 for row in ring_rows)
        lo = ((displayed - 0.05) * total - ring_sum) / (total - len(ring_rows))
        hi = ((displayed + 0.05) * total - ring_sum) / (total - len(ring_rows))
        overall = {
            "displayed": displayed,
            "total_as_displayed": total,
            "low": round(lo, 2),
            "high": round(hi, 2),
            "no_visible_change": lo <= displayed <= hi,
        }
    ratings = {
        "examined": examined,
        "sample_mean": sample_mean,
        "without_ring": without_ring,
        "without_ring_and_suspicious": strict,
        "ring_reviews": len(ring_rows),
        "overall": overall,
    }

    # ---------------------------------------------------------------- level
    young = young_business(inp, bursts)
    rings = [g for g in groups if g.verdict == "ring"]
    possibles = [g for g in groups if g.verdict in ("possible_ring", "possible_ring_trip")]
    level_cfg = config.load_tunables()["level"]
    reasons: list[str] = []
    ring_share = len(ring_rows) / examined if examined else 0.0
    suspicious_share = label_counts.get("suspicious", 0) / examined if examined else 0.0
    ok_histories = sum(1 for c in expanded if inp.contributors.get(c) and inp.contributors[c].status == "ok")
    strong = [g for g in rings if (g.confidence or 0) >= level_cfg["high_confidence"]]
    if strong and ring_share >= level_cfg["high_ring_share"]:
        level = "High"
        reasons.append(
            f"A ring of {len(strong[0].members)} accounts (confidence {strong[0].confidence:.2f}) wrote "
            f"{len(ring_rows)} of the {examined} reviews examined."
        )
    elif rings or possibles or suspicious_share >= level_cfg["elevated_suspicious_share"]:
        level = "Elevated"
        if rings:
            reasons.append(f"{_plural(len(rings), 'ring-like group')} found among the reviewers checked.")
        if possibles:
            reasons.append(f"{_plural(len(possibles), 'possible ring')} found (weighted lower).")
        if suspicious_share >= level_cfg["elevated_suspicious_share"]:
            reasons.append(
                f"{label_counts['suspicious']} of {examined} reviews come from accounts with copied text "
                "and other signals."
            )
    elif expanded and ok_histories == 0:
        level = "Not enough history"
        reasons.append("Every reviewer history checked was empty or private, so nothing could be compared.")
    elif young["young"]:
        level = "Not enough history"
        reasons.append("This business has too short a review history to judge.")
    else:
        level = "Low"
        reasons.append("No ring-like pattern among the highest-priority reviewers checked.")

    # ---------------------------------------------------------------- client lists
    client_lists = {
        g.group_id: client_list(inp, g) for g in groups if g.verdict in ("ring", "possible_ring", "possible_ring_trip")
    }

    # ---------------------------------------------------------------- evidence
    t4 = target_duplicate_clusters(inp.target_reviews, features, target_only=False)
    t4 = {k: v for k, v in t4.items() if k not in stock}
    evidence = evidence_sentences(inp, groups, client_lists, bursts, t4, ratings, expanded, edge_pairs)

    popular_target = is_popular_type(inp.target.type)
    warnings = []
    if popular_target:
        warnings.append("Co-visits are normal for popular places, so this analysis is less reliable.")
    if young["young"]:
        warnings.append("Young business: its review history is short.")
    if inp.target.lat is None:
        warnings.append("The business's location is unknown, so distances couldn't be used.")

    baseline = [e.contributor_id for e in inp.expansions if e.reason == "baseline"]
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "place": {
            "place_key": inp.target.place_key,
            "title": inp.target.title,
            "type": inp.target.type,
            "type_group": type_group(inp.target.type)[0],
            "area": inp.target.area,
            "lat": inp.target.lat,
            "lng": inp.target.lng,
            "rating": inp.target.rating,
            "total_reviews": inp.target.total_reviews,
        },
        "sample": {
            "examined": examined,
            "first": min((row["day"] for row in review_rows if row["day"]), default=None),
            "last": max((row["day"] for row in review_rows if row["day"]), default=None),
            "expanded": len(expanded),
            "histories_ok": ok_histories,
            "baseline": baseline,
            "not_checked_high_priority": 0,
        },
        "warnings": warnings,
        "level": {"level": level, "reasons": reasons},
        "ratings": ratings,
        "signals": {
            "T1": bursts.as_dict(),
            "T2": rating_histogram(inp.target_reviews),
            "T3": thin_profile_skew(inp.target_reviews),
            "T4": {"clusters": t4, "stock_phrase_clusters": sorted(stock)},
            "T5": young,
        },
        "reviewers": [
            {
                "contributor_id": cid,
                "round": next(e.round for e in inp.expansions if e.contributor_id == cid),
                "reason": next(e.reason for e in inp.expansions if e.contributor_id == cid),
                "status": inp.contributors[cid].status if cid in inp.contributors else "missing",
                "label": reviewer_label[cid],
                "group": membership[cid].group_id if cid in membership else None,
                "truncated": bool(inp.contributors.get(cid) and inp.contributors[cid].truncated),
                "visible_reviews": len(inp.histories.get(cid, [])),
                "total_reviews": inp.contributors[cid].total_reviews if cid in inp.contributors else None,
                **signals[cid].as_dict(),
            }
            for cid in expanded
        ],
        "graph": graph_payload(inp, expanded, all_pairs, edge_pairs, reviewer_label),
        "groups": [g.as_dict() for g in groups],
        "reviews": review_rows,
        "label_counts": {k: label_counts.get(k, 0) for k in LABELS},
        "client_lists": client_lists,
        "places": places_payload(inp, groups),
        "evidence": evidence,
        "caveats": caveats(inp),
        "notes": inp.notes,
    }


def client_list(inp: AnalysisInput, g: Group) -> list[dict[str, Any]]:
    """ "Also reviewed by this group": core places plus any place reviewed by >= 2 members."""
    by_place: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for cid in g.members:
        for h in inp.histories.get(cid, []):
            if h.place_key and h.place_key != inp.target.place_key:
                by_place[h.place_key][cid].append(h)
    rows = []
    for key, who in by_place.items():
        if len(who) < 2 and key not in g.core_places:
            continue
        place = inp.places.get(key)
        reviews = [h for hs in who.values() for h in hs]
        dated = [h for h in reviews if h.date_min is not None]
        rated = [h.rating for h in reviews if h.rating is not None]
        rows.append(
            {
                "place_key": key,
                "title": place.title if place else None,
                "area": place.area if place else None,
                "type": place.type if place else None,
                "type_group": type_group(place.type if place else None)[0],
                "lat": place.lat if place else None,
                "lng": place.lng if place else None,
                "distance_km": None
                if not place or distance_km(inp.target, place) is None
                else round(distance_km(inp.target, place)),  # type: ignore[arg-type]
                "core": key in g.core_places,
                "members": sorted(who),
                "member_count": len(who),
                "date_from": min(h.date_min for h in dated).isoformat() if dated else None,
                "date_to": max(h.date_max for h in dated).isoformat() if dated else None,
                "avg_rating": round(statistics.fmean(rated), 2) if rated else None,
            }
        )
    rows.sort(key=lambda r: (-r["member_count"], not r["core"], r["place_key"]))
    return rows


def graph_payload(inp, expanded, all_pairs, edge_pairs, labels) -> dict[str, Any]:
    nodes = [{"id": cid, "label": labels[cid]} for cid in expanded]
    links = []
    for (u, v), p in sorted(all_pairs.items()):
        if (u, v) not in edge_pairs:
            continue
        links.append(
            {
                "source": u,
                "target": v,
                "weight": round(p.weight, 3),
                "shared": [
                    {
                        "place_key": s.place_key,
                        "surprise": s.surprise,
                        "coincidence": s.coincidence,
                        "popular": s.popular,
                    }
                    for s in p.shared
                ],
            }
        )
    return {"nodes": nodes, "edges": links}


def places_payload(inp: AnalysisInput, groups: list[Group]) -> dict[str, dict[str, Any]]:
    """Places referenced by groups and edges, for the map and tables."""
    keys = {inp.target.place_key}
    for g in groups:
        keys.update(g.core_places)
    out = {}
    for k in sorted(keys):
        p = inp.places.get(k)
        if p is None:
            continue
        out[k] = {
            "title": p.title,
            "area": p.area,
            "type": p.type,
            "type_group": type_group(p.type)[0],
            "lat": p.lat,
            "lng": p.lng,
            "surprise": surprise(inp.target, p),
        }
    return out


def evidence_sentences(inp, groups, client_lists, bursts, t4, ratings, expanded, edge_pairs) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    examined = ratings["examined"]
    for g in groups:
        m = g.metrics
        if g.verdict in ("ring", "possible_ring"):
            text = (
                f"{_plural(len(g.members), 'account')} that reviewed this business also reviewed the same "
                f"{_plural(m['core_places'], 'other business', 'other businesses')} in "
                f"{_plural(m['far_area_count'], 'different city', 'different cities')}"
            )
            if m["co_timing_ratio"] is not None and m["co_timing_ratio"] >= 0.5:
                text += ", mostly within the same week"
            out.append({"kind": "ring", "group": g.group_id, "text": text + ".", "visual": "graph"})
        elif g.verdict == "possible_ring_trip":
            out.append(
                {
                    "kind": "possible_ring_trip",
                    "group": g.group_id,
                    "visual": "graph",
                    "text": f"{_plural(len(g.members), 'reviewer')} share only travel businesses in one region, but "
                    "their histories are mostly these places and their ratings are almost all 5★. This could "
                    "be a group trip or a regional ring (possible ring, trip-like pattern).",
                }
            )
        elif g.verdict == "ruled_out_trip":
            out.append(
                {
                    "kind": "ruled_out_trip",
                    "group": g.group_id,
                    "visual": "ruled_out",
                    "text": f"{_plural(len(g.members), 'reviewer')} share travel businesses within one region, and "
                    "their histories look like ordinary travellers'. Consistent with a group trip; not counted.",
                }
            )
    for b in bursts.bursts:
        weekly = bursts.baseline_per_window / 3 * 7 if bursts.baseline_per_window else None
        normal = f" (normally about {max(1, round(weekly))} a week)" if weekly else ""
        star = "5★" if b.direction == "positive" else "1★"
        span_days = (b.end - b.start).days + 1
        out.append(
            {
                "kind": "burst",
                "visual": "timeline",
                "text": f"{b.count} of the latest {examined} reviews arrived within "
                f"{_plural(span_days, 'day')}{normal}; "
                f"{b.matching} of them are {star}. Consistent with an in-store review drive or a campaign.",
            }
        )
    dup_reviews = sum(len(v) for v in t4.values())
    if dup_reviews:
        out.append(
            {"kind": "duplicates", "visual": "reviews", "text": f"{dup_reviews} review texts are near-identical."}
        )
    baseline = [e.contributor_id for e in inp.expansions if e.reason == "baseline"]
    for g in groups:
        if g.verdict not in ("ring", "possible_ring") or not baseline:
            continue
        linked = [b for b in baseline if any(tuple(sorted((b, m))) in edge_pairs for m in g.members)]
        shared_any = [b for b in baseline if any(h.place_key in set(g.core_places) for h in inp.histories.get(b, []))]
        if not linked and not shared_any:
            out.append(
                {
                    "kind": "baseline",
                    "visual": "graph",
                    "text": f"The {_plural(len(baseline), 'randomly chosen reviewer')} shared no other places "
                    "with this group.",
                }
            )
        break
    return out


def caveats(inp: AnalysisInput) -> list[str]:
    n = inp.params.get("n") or len(inp.target_reviews)
    k = len(inp.expansions)
    return [
        "This is a pattern, not proof.",
        f"Only the newest {n} reviews and the {k} highest-priority reviewers were examined.",
        "Private profiles can't be checked.",
        "Dates in reviewer histories are approximate.",
        "Rings within a single city aren't detected.",
        "Google may already have removed some reviews.",
    ]

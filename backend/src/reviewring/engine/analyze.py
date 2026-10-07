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
from .accounts import AccountSignals, compute_signals
from .features import compute_text_features, target_text_id
from .graph import build_pairs, distance_km, edges, is_popular_type, surprise
from .groups import Group, detect_groups, type_group
from .homes import compute_homes
from .signs import ai_coverage, first_time_skew, review_signs, sieve_summary
from .target_signals import (
    detect_bursts,
    generated_excerpt,
    generated_marker,
    rating_gap,
    rating_histogram,
    single_use_bursts,
    target_duplicate_clusters,
    thin_profile_skew,
    top_rated_sample,
    young_business,
)

EVIDENCE_ORDER = {
    k: i
    for i, k in enumerate(
        [
            "ring",
            "possible_ring",
            "generated_text",
            "single_use_burst",
            "rating_gap",
            "top_rated",
            "ai_style",
            "first_time_skew",
            "possible_ring_trip",
            "duplicates",
            "burst",
            "baseline",
            "social_circle",
            "ruled_out_trip",
        ]
    )
}
LABELS = ["ring", "possible_ring_trip", "suspicious", "single_use_burst", "group_trip", "no_flags", "not_checked"]
LABEL_TEXT = {
    "ring": "Ring-like group",
    "possible_ring_trip": "Possible ring-like group (trip-like)",
    "suspicious": "Suspicious",
    "single_use_burst": "First-time account in a burst",
    "group_trip": "Trip or social group",
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


def stock_phrase_clusters(inp: AnalysisInput, features, edge_pairs, checked: set[str]) -> set[str]:
    """Clusters used by >= N accounts where < 20% of the *checked* users have an edge to another user of it.

    Only checked (expanded) accounts can have edges, so the share is computed among them; with fewer than
    3 checked users it's undetermined and the cluster is kept as evidence rather than dismissed.
    """
    cfg = config.load_tunables()["text"]
    owners = cluster_owners(features.values())
    out = set()
    for cluster, accounts in owners.items():
        if len(accounts) < cfg["stock_phrase_min_accounts"]:
            continue
        known = [a for a in accounts if a in checked]
        if len(known) < cfg.get("stock_phrase_min_checked", 3):
            continue
        connected = sum(1 for a in known if any(tuple(sorted((a, b))) in edge_pairs for b in known if b != a))
        if connected / len(known) < cfg["stock_phrase_max_connected_share"]:
            out.add(cluster)
    return out


def analyze(inp: AnalysisInput, paraphrase_groups: dict[str, int] | None = None) -> dict[str, Any]:
    features = compute_text_features(inp)
    bursts = detect_bursts(inp.target_reviews)
    expanded = [e.contributor_id for e in inp.expansions]
    usable = [c for c in expanded if inp.contributors.get(c) and inp.contributors[c].status == "ok"]
    homes = compute_homes(inp, usable)
    all_pairs = build_pairs(inp, usable, homes)
    edge_pairs = edges(all_pairs)
    stock = stock_phrase_clusters(inp, features, edge_pairs, set(usable))
    signals = compute_signals(inp, features, bursts, stock, paraphrase_groups)
    groups = detect_groups(inp, edge_pairs, signals, homes)

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
        elif g is not None and g.verdict in ("ruled_out_trip", "social_circle"):
            reviewer_label[cid] = "group_trip"
        else:
            reviewer_label[cid] = "no_flags"

    single_bursts = single_use_bursts(inp.target_reviews, bursts)
    single_ids = {i for b in single_bursts if b["flagged"] for i in b["review_ids"]}

    review_rows = []
    for r in inp.target_reviews:
        label = reviewer_label.get(r.contributor_id or "", "not_checked")
        if r.review_id in single_ids and label in ("no_flags", "not_checked", "group_trip"):
            label = "single_use_burst"
        f = features.get(target_text_id(r.review_id))
        marker = generated_marker(r)
        judgement = inp.text_judgements.get(r.review_id)
        signs = review_signs(
            r,
            marker=marker,
            copied=bool(f and f.cluster and f.cluster not in stock),
            in_first_time_burst=r.review_id in single_ids,
            label=label,
            judgement=judgement,
            spree=bool(r.contributor_id in signals and signals[r.contributor_id].has("A9")),
        )
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
                "generated_marker": marker,
                "excerpt": generated_excerpt(r),
                "signs": signs,
                "ai": None
                if judgement is None
                else {"verdict": judgement.get("verdict"), "cues": judgement.get("cues", [])},
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
    strict = mean(
        [
            row
            for row in review_rows
            if row["label"] not in ("ring", "suspicious", "possible_ring_trip", "single_use_burst")
        ]
    )
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
    sieve = sieve_summary(review_rows, ai_coverage(inp.target_reviews, inp.text_judgements))
    ratings = {
        "examined": examined,
        "sample_mean": sample_mean,
        "kept_mean": sieve["kept"]["mean"],
        "kept_count": sieve["kept"]["count"],
        "without_ring": without_ring,
        "without_ring_and_suspicious": strict,
        "ring_reviews": len(ring_rows),
        "single_use_burst_reviews": len(single_ids),
        "overall": overall,
    }

    # ---------------------------------------------------------------- level
    young = young_business(inp, bursts)
    gap = rating_gap(inp)
    top = top_rated_sample(inp)
    generated = [row for row in review_rows if row["generated_marker"]] + (top.get("generated") or [])
    generated_ids = {g["review_id"] for g in generated}
    raise_generated = bool(generated_ids) and config.tunable("generated_text", "raises_level")
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
            f"A ring-like group of {len(strong[0].members)} accounts "
            f"(evidence strength {strong[0].confidence:.2f}) wrote "
            f"{len(ring_rows)} of the {examined} reviews examined."
        )
    elif (
        rings
        or possibles
        or suspicious_share >= level_cfg["elevated_suspicious_share"]
        or (single_ids and config.tunable("single_use", "raises_level"))
        or raise_generated
    ):
        level = "Elevated"
        if rings:
            reasons.append(f"{_plural(len(rings), 'ring-like group')} found among the reviewers checked.")
        if possibles:
            reasons.append(f"{_plural(len(possibles), 'possible ring-like group')} found (weighted lower).")
        if suspicious_share >= level_cfg["elevated_suspicious_share"]:
            reasons.append(
                f"{label_counts['suspicious']} of {examined} reviews come from accounts with copied text "
                "and other signals."
            )
        if raise_generated:
            reasons.append(
                f"{_plural(len(generated_ids), 'review')} {'contains' if len(generated_ids) == 1 else 'contain'} "
                "text that only a chatbot or an unfilled "
                "template would produce, pasted in as a customer review."
            )
        for b in single_bursts:
            if b["flagged"]:
                star = "5★" if b["direction"] == "positive" else "1★"
                reasons.append(
                    f"A burst of {b['count']} {star} reviews ({b['start']} to {b['end']}): {b['single_use']} came "
                    "from accounts that have reviewed nothing else."
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
    evidence += rating_evidence(gap, top, [row for row in review_rows if row["generated_marker"]])
    skew = first_time_skew(inp.target_reviews)
    evidence += review_text_evidence(sieve, skew)
    evidence.sort(key=lambda e: EVIDENCE_ORDER.get(e["kind"], len(EVIDENCE_ORDER)))  # stable: the strongest first

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
            "T6": {"single_use_bursts": single_bursts},
            "T7": gap,
            "T8": top,
            "T9": skew,
        },
        "sieve": sieve,
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
        "histories": histories_payload(inp, expanded, homes),
        "graph": graph_payload(inp, expanded, all_pairs, edge_pairs, reviewer_label),
        "groups": [g.as_dict() for g in groups],
        "reviews": review_rows,
        "label_counts": {k: label_counts.get(k, 0) for k in LABELS},
        "client_lists": client_lists,
        "places": places_payload(inp, groups, signals),
        "evidence": evidence,
        "caveats": caveats(inp, sieve["ai"]),
        "calibration": date_calibration(inp),
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


def histories_payload(inp: AnalysisInput, expanded: list[str], homes: dict) -> dict[str, dict[str, Any]]:
    """Each checked reviewer's visible history, compact, for the reviewer views: when, how many stars, where."""
    out: dict[str, dict[str, Any]] = {}
    for cid in expanded:
        c = inp.contributors.get(cid)
        if c is None or c.status != "ok":
            continue
        items = []
        for h in inp.histories.get(cid, []):
            place = inp.places.get(h.place_key) if h.place_key else None
            km = distance_km(inp.target, place) if place is not None else None
            mid = None
            if h.date_min is not None and h.date_max is not None:
                mid = h.date_min + (h.date_max - h.date_min) / 2
            items.append(
                {
                    "day": mid.isoformat() if mid else None,
                    "rating": h.rating,
                    "place_key": h.place_key,
                    "this": h.place_key == inp.target.place_key,
                    "area": place.area if place else None,
                    "type_group": type_group(place.type if place else None)[0],
                    "lat": None if place is None or place.lat is None else round(place.lat, 2),
                    "lng": None if place is None or place.lng is None else round(place.lng, 2),
                    "km": None if km is None else round(km, 1),
                }
            )
        items.sort(key=lambda x: x["day"] or "")
        home = homes.get(cid)
        out[cid] = {
            "total_reviews": c.total_reviews,
            "visible": len(items),
            "home_area": home.area if home else None,
            "items": items,
        }
    return out


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


def places_payload(
    inp: AnalysisInput, groups: list[Group], signals: dict[str, AccountSignals]
) -> dict[str, dict[str, Any]]:
    """Places referenced by groups and same-day-distant badges, for the map and tables."""
    keys = {inp.target.place_key}
    for g in groups:
        keys.update(g.core_places)
    for sig in signals.values():
        for occ in sig.badges.get("A4", {}).get("occasions", []):
            keys.update(occ["places"])
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
    for b in single_use_bursts(inp.target_reviews, bursts):
        if b["flagged"]:
            out.append(
                {
                    "kind": "single_use_burst",
                    "visual": "timeline",
                    "text": f"{b['single_use']} of the {b['count']} reviews in the {b['start']} to {b['end']} "
                    "burst came from accounts that have reviewed nothing else on Google Maps. Bursts of "
                    "first-time accounts are a common pattern in coordinated review campaigns, though a business "
                    "can also be targeted without its knowledge.",
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


def rating_evidence(gap: dict[str, Any], top: dict[str, Any], recent_generated: list[dict[str, Any]]) -> list:
    out: list[dict[str, Any]] = []
    if gap.get("flagged"):
        out.append(
            {
                "kind": "rating_gap",
                "visual": "timeline",
                "text": f"The business shows {gap['displayed']}★ from {gap['total']:,} reviews, but its latest "
                f"{gap['recent_count']} average {gap['recent_mean']}★. For the display to hold, the other "
                f"{gap['older_count']:,} must average about {gap['older_implied_mean']}★.",
            }
        )
    if top.get("available"):
        parts = [
            f"Of {top['count']} highest-rated reviews sampled, {top['window_count']} were posted between "
            f"{top['window_start']} and {top['window_end']}"
        ]
        if top.get("single_use_share") is not None:
            parts.append(f"{round(top['single_use_share'] * 100)}% come from accounts with at most one review")
        out.append({"kind": "top_rated", "visual": "reviews", "text": "; ".join(parts) + "."})
    gen = (top.get("generated") or []) + [
        {"rating": r["rating"], "day": r["day"], "marker": r["generated_marker"]} for r in recent_generated
    ]
    for g in gen[:3]:
        out.append(
            {
                "kind": "generated_text",
                "visual": "reviews",
                "text": f'A {g["rating"]:.0f}★ review from {g["day"]} contains "{g["marker"]}", text that only a '
                "chatbot or an unfilled template would produce, pasted in as a customer review.",
            }
        )
    return out


def caveats(inp: AnalysisInput, ai: dict[str, Any] | None = None) -> list[str]:
    n = len(inp.target_reviews)
    k = len(inp.expansions)
    out = [
        "This is a pattern, not proof.",
        f"Only the newest {n} reviews and the {k} highest-priority reviewers were examined.",
        "Private profiles can't be checked.",
        "Dates in reviewer histories are approximate.",
        "Rings within a single city aren't detected.",
        "Google may already have removed some reviews.",
        "A business can be targeted without its knowledge: review-task scams hand recruits real businesses to review.",
    ]
    if ai and ai.get("judged"):
        out.append(
            "\u201cReads as AI-written\u201d is an AI model's opinion. AI-text detectors are unreliable on short texts "
            "and over-flag people writing in a second language, so only longer reviews were judged."
        )
    return out


def review_text_evidence(sieve: dict[str, Any], skew: dict[str, Any]) -> list[dict[str, Any]]:
    """Sentences for the AI-written opinion and for first-time accounts concentrated among 5-star reviews."""
    out: list[dict[str, Any]] = []
    ai = sieve["ai"]
    n_ai = sieve["signs"].get("ai_style", {}).get("count", 0)
    if ai.get("judged") and n_ai:
        out.append(
            {
                "kind": "ai_style",
                "visual": "sieve",
                "text": f"{n_ai} of the {ai['judged']} reviews long enough to judge read as AI-written to an AI model, "
                "which quotes the phrases behind each opinion. Real customers also polish honest reviews with AI, "
                "so these are shown, not counted.",
            }
        )
    if skew.get("flagged"):
        five, other = skew["five_star"], skew["other"]
        f5, fo = skew["five_star_first_time"], skew["other_first_time"]
        out.append(
            {
                "kind": "first_time_skew",
                "visual": "sieve",
                "text": f"{f5} of the {five} five-star reviews ({round(100 * f5 / five)}%) come from accounts with no "
                f"other reviews, against {fo} of the {other} other reviews ({round(100 * fo / other)}%). "
                "Customers asked to review on the spot also create new accounts, so this is context, not proof.",
            }
        )
    return out


def date_calibration(inp: AnalysisInput) -> list[dict[str, Any]]:
    """Free calibration of relative dates: each checked reviewer's history usually contains their review of
    this business, whose exact date we already have. Compare the estimated range with the true date."""
    exact = {r.contributor_id: r.posted_at for r in inp.target_reviews if r.contributor_id and r.posted_at}
    rows = []
    for cid, history in sorted(inp.histories.items()):
        true = exact.get(cid)
        if true is None:
            continue
        for h in history:
            if h.place_key == inp.target.place_key and h.date_min is not None:
                day = ist_date(true)
                rows.append(
                    {
                        "relative": h.relative_date,
                        "true_date": day.isoformat(),
                        "estimated_from": h.date_min.isoformat(),
                        "estimated_to": h.date_max.isoformat() if h.date_max else None,
                        "inside": h.date_min <= day <= (h.date_max or h.date_min),
                    }
                )
                break
    return rows

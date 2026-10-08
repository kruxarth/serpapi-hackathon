"""Which reviewers to expand (spec 9.3). Expanding one reviewer costs 1 search."""

from __future__ import annotations

import random
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import timedelta

from .. import config
from ..model import TargetReview
from ..normalize.text import TextFeatures
from .features import target_text_id
from .target_signals import BurstResult


@dataclass
class Candidate:
    contributor_id: str
    review_id: str
    score: int
    posted_ts: float  # for "ties go to the newest review"
    parts: dict[str, int] = field(default_factory=dict)


def score_reviews(
    reviews: list[TargetReview],
    bursts: BurstResult,
    features: dict[str, TextFeatures],
    keyword_ids: frozenset[str] | set[str] = frozenset(),
) -> list[Candidate]:
    """One candidate per contributor (their highest-scoring review), best first. ``keyword_ids``: reviews written like
    search ads, whose authors are worth opening first so their own writing can be compared."""
    w = config.load_tunables()["priority"]
    dup_clusters: dict[str, int] = {}
    for r in reviews:
        f = features.get(target_text_id(r.review_id))
        if f and f.target_cluster:
            dup_clusters[f.target_cluster] = dup_clusters.get(f.target_cluster, 0) + 1

    five_star_times = sorted(r.posted_at for r in reviews if r.rating == 5 and r.posted_at is not None)
    window = timedelta(hours=float(w.get("batch_window_hours", 24)))

    def batch_size(r: TargetReview) -> int:
        """Other 5-star reviews within +-24 h: catches small batches a busy place's burst test misses."""
        if r.posted_at is None:
            return 0
        lo, hi = bisect_left(five_star_times, r.posted_at - window), bisect_right(five_star_times, r.posted_at + window)
        return hi - lo - (1 if r.rating == 5 else 0)

    best: dict[str, Candidate] = {}
    for r in reviews:
        if not r.contributor_id:
            continue
        parts: dict[str, int] = {}
        burst = bursts.burst_for(r)
        if burst is not None:
            parts["in_burst"] = w["in_burst"]
            if r.rating == (5 if burst.direction == "positive" else 1):
                parts["rating_matches_direction"] = w["rating_matches_direction"]
        elif r.rating == 5:
            parts["rating_matches_direction"] = w["rating_matches_direction"]
        if r.rating == 5 and burst is None and batch_size(r) >= w.get("batch_min_others", 2):
            parts["batch"] = w.get("batch_points", 2)
        if r.reviewer_reviews is not None and r.reviewer_reviews <= w["thin_reviews_max"]:
            parts["thin_reviewer"] = w["thin_reviewer"]
        if r.reviewer_photos is not None and r.reviewer_photos == 0:
            parts["zero_photos"] = w["zero_photos"]
        f = features.get(target_text_id(r.review_id))
        if f is not None and f.short:
            parts["short_text"] = w["short_text"]
        if f is not None and f.target_cluster and dup_clusters.get(f.target_cluster, 0) >= 2:
            parts["duplicate_cluster"] = w["duplicate_cluster"]
        if r.review_id in keyword_ids:
            parts["keyword_style"] = int(config.tunable("keyword_style", "priority_points"))
        if r.local_guide and w["local_guide"]:
            parts["local_guide"] = w["local_guide"]
        cand = Candidate(
            r.contributor_id,
            r.review_id,
            sum(parts.values()),
            r.posted_at.timestamp() if r.posted_at else float("-inf"),
            parts,
        )
        prev = best.get(r.contributor_id)
        if prev is None or (cand.score, cand.posted_ts) > (prev.score, prev.posted_ts):
            best[r.contributor_id] = cand
    return sorted(best.values(), key=lambda c: (-c.score, -c.posted_ts, c.contributor_id))


@dataclass
class Selection:
    round1: list[str]  # priority picks
    baseline: list[str]
    remaining: list[Candidate]  # ranked, for round 2
    voice: list[str] = field(default_factory=list)  # authors of long reviews, opened to compare their voice


def select_round1(candidates: list[Candidate], seed_key: str, k1: int, b: int) -> Selection:
    """Top K1 by score plus B random baseline reviewers from the lower-scoring half (fixed seed)."""
    if len(candidates) <= k1 + b:
        return Selection([c.contributor_id for c in candidates], [], [])
    top = candidates[:k1]
    lower_half = candidates[len(candidates) // 2 :]
    pool = [c for c in lower_half if c not in top]
    rng = random.Random(f"{config.tunable('collection', 'seed')}:{seed_key}")
    baseline = rng.sample(pool, min(b, len(pool))) if pool else []
    baseline.sort(key=lambda c: c.contributor_id)
    chosen = {c.contributor_id for c in top} | {c.contributor_id for c in baseline}
    return Selection(
        [c.contributor_id for c in top],
        [c.contributor_id for c in baseline],
        [c for c in candidates if c.contributor_id not in chosen],
    )


def select_round2(
    selection: Selection,
    reviews: list[TargetReview],
    features: dict[str, TextFeatures],
    k2: int,
) -> list[str]:
    """Next K2 by score, with a bonus for reviewers near a round-1 pick in time or text."""
    w = config.load_tunables()["priority"]
    bonus = int(w.get("round2_bonus", 2))
    near = timedelta(days=int(w["round2_near_days"]))
    by_review = {r.review_id: r for r in reviews}
    by_contributor: dict[str, list[TargetReview]] = {}
    for r in reviews:
        if r.contributor_id:
            by_contributor.setdefault(r.contributor_id, []).append(r)
    picks = [r for cid in selection.round1 for r in by_contributor.get(cid, [])]
    pick_times = [r.posted_at for r in picks if r.posted_at]
    pick_clusters = {
        features[target_text_id(r.review_id)].target_cluster
        for r in picks
        if target_text_id(r.review_id) in features and features[target_text_id(r.review_id)].target_cluster
    }

    def adjusted(c) -> tuple[int, float, str]:
        r = by_review.get(c.review_id)
        extra = 0
        if r is not None:
            close = r.posted_at is not None and any(abs(r.posted_at - t) <= near for t in pick_times)
            f = features.get(target_text_id(r.review_id))
            dup = f is not None and f.target_cluster in pick_clusters
            if close or dup:
                extra = bonus
        return (-(c.score + extra), -c.posted_ts, c.contributor_id)

    return [c.contributor_id for c in sorted(selection.remaining, key=adjusted)[:k2]]


def select_voice(
    reviews: list[TargetReview], exclude: set[str], k: int, keyword_ids: frozenset[str] | set[str] = frozenset()
) -> list[str]:
    """Authors worth opening to compare their voice: the longest 4-5 star reviews from accounts that have other
    reviews, search-ad phrasing first. The priority score favours thin, short and bursty reviews, which leave
    nothing to compare."""
    cfg = config.load_tunables()["voice"]
    pool = [
        r
        for r in reviews
        if r.contributor_id
        and r.contributor_id not in exclude
        and (r.rating or 0) >= 4
        and r.text
        and len(r.text.split()) >= int(cfg["pick_min_words"])
        and (r.reviewer_reviews or 0) >= int(cfg["pick_min_account_reviews"])
    ]
    pool.sort(key=lambda r: (r.review_id not in keyword_ids, -len(r.text.split()), r.contributor_id))  # type: ignore[union-attr]
    out: list[str] = []
    for r in pool:
        if r.contributor_id not in out:
            out.append(r.contributor_id)  # type: ignore[arg-type]
        if len(out) >= k:
            break
    return out

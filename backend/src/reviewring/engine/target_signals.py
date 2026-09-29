"""Target-level signals T1-T5 (spec 9.2). Free: they use the target's reviews only."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from scipy.stats import poisson

from .. import config
from ..model import AnalysisInput, TargetReview
from ..normalize.dates import ist_date
from ..normalize.text import TextFeatures
from .features import target_text_id


@dataclass
class Burst:
    start: date
    end: date  # inclusive
    direction: str  # positive | negative
    count: int
    matching: int  # reviews in the burst's direction (5-star or 1-star)
    p_value: float
    review_ids: list[str] = field(default_factory=list)

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["start"], out["end"] = self.start.isoformat(), self.end.isoformat()
        return out


@dataclass
class BurstResult:
    skipped: bool
    reason: str | None
    span_days: int
    n_dated: int
    baseline_per_window: float | None
    bursts: list[Burst]

    def burst_for(self, review: TargetReview) -> Burst | None:
        if review.posted_at is None:
            return None
        d = ist_date(review.posted_at)
        return next((b for b in self.bursts if b.contains(d)), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "skipped": self.skipped,
            "reason": self.reason,
            "span_days": self.span_days,
            "n_dated": self.n_dated,
            "baseline_per_window": self.baseline_per_window,
            "baseline_per_week": None
            if self.baseline_per_window is None
            else self.baseline_per_window / float(config.tunable("bursts", "window_days")) * 7,
            "bursts": [b.as_dict() for b in self.bursts],
        }


def detect_bursts(reviews: list[TargetReview]) -> BurstResult:
    cfg = config.load_tunables()["bursts"]
    dated = [(ist_date(r.posted_at), r) for r in reviews if r.posted_at is not None]
    if not dated:
        return BurstResult(True, "no dated reviews", 0, 0, None, [])
    first = min(d for d, _ in dated)
    last = max(d for d, _ in dated)
    span = (last - first).days + 1
    if len(dated) < cfg["min_reviews"] or span < cfg["min_span_days"]:
        reason = f"only {len(dated)} reviews" if len(dated) < cfg["min_reviews"] else f"reviews span {span} day(s)"
        return BurstResult(True, reason, span, len(dated), None, [])

    width = int(cfg["window_days"])
    by_day: dict[date, list[TargetReview]] = {}
    for d, r in dated:
        by_day.setdefault(d, []).append(r)
    starts = [first + timedelta(days=i) for i in range(max(1, span - width + 1))]

    def window(start: date) -> list[TargetReview]:
        return [r for i in range(width) for r in by_day.get(start + timedelta(days=i), [])]

    lam = len(dated) / span * width
    flagged: dict[date, tuple[str, int, float]] = {}
    for _ in range(int(cfg["max_rounds"])):
        new: dict[date, tuple[str, int, float]] = {}
        for s in starts:
            rs = window(s)
            n = len(rs)
            if n < cfg["window_min_reviews"]:
                continue
            p = float(poisson.sf(n - 1, lam))
            if p >= cfg["poisson_p"]:
                continue
            five = sum(1 for r in rs if r.rating == 5)
            one = sum(1 for r in rs if r.rating == 1)
            if five / n >= cfg["direction_share"]:
                new[s] = ("positive", five, p)
            elif cfg["negative_bursts"] and one / n >= cfg["direction_share"]:
                new[s] = ("negative", one, p)
        if new.keys() == flagged.keys():
            flagged = new
            break
        flagged = new
        excluded = {s + timedelta(days=i) for s in flagged for i in range(width)}
        excluded &= {first + timedelta(days=i) for i in range(span)}
        rest_days = span - len(excluded)
        rest_reviews = sum(1 for d, _ in dated if d not in excluded)
        if rest_days > 0:
            lam = max(rest_reviews, 1) / rest_days * width  # at least one review, so lambda never hits zero

    bursts: list[Burst] = []
    for s in sorted(flagged):
        direction, _, p = flagged[s]
        end = s + timedelta(days=width - 1)
        if bursts and bursts[-1].direction == direction and s <= bursts[-1].end:
            b = bursts[-1]
            b.end = max(b.end, end)
            b.p_value = min(b.p_value, p)
        else:
            bursts.append(Burst(s, end, direction, 0, 0, p))
    for b in bursts:
        rs = [r for d, r in dated if b.contains(d)]
        b.count = len(rs)
        b.matching = sum(1 for r in rs if r.rating == (5 if b.direction == "positive" else 1))
        b.review_ids = sorted(r.review_id for r in rs)
    return BurstResult(False, None, span, len(dated), lam, bursts)


def rating_histogram(reviews: list[TargetReview]) -> dict[str, int]:
    counts = Counter(r.rating for r in reviews if r.rating in (1, 2, 3, 4, 5))
    return {str(i): counts.get(i, 0) for i in range(1, 6)}


def thin_profile_skew(reviews: list[TargetReview]) -> dict[str, Any]:
    thin_max = int(config.tunable("priority", "thin_reviews_max"))

    def bucket(rs: list[TargetReview]) -> dict[str, Any]:
        known = [r for r in rs if r.reviewer_reviews is not None]
        thin = sum(1 for r in known if r.reviewer_reviews <= thin_max)  # type: ignore[operator]
        return {
            "reviews": len(rs),
            "known": len(known),
            "unknown": len(rs) - len(known),
            "thin": thin,
            "thin_share": thin / len(known) if known else None,
        }

    return {
        "thin_max_reviews": thin_max,
        "five_star": bucket([r for r in reviews if r.rating == 5]),
        "low_star": bucket([r for r in reviews if r.rating is not None and r.rating <= 3]),
    }


def target_duplicate_clusters(
    reviews: list[TargetReview], features: dict[str, TextFeatures], *, target_only: bool
) -> dict[str, list[str]]:
    """Clusters with at least 2 of the target's reviews. ``target_only`` uses the pre-history clusters."""
    out: dict[str, list[str]] = {}
    for r in reviews:
        f = features.get(target_text_id(r.review_id))
        cluster = (f.target_cluster if target_only else f.cluster) if f else None
        if cluster:
            out.setdefault(cluster, []).append(r.review_id)
    return {k: sorted(v) for k, v in sorted(out.items()) if len(v) >= 2}


def young_business(inp: AnalysisInput, bursts: BurstResult) -> dict[str, Any]:
    cfg = config.load_tunables()["young"]
    total = inp.target.total_reviews
    few = total is not None and total < cfg["min_total_reviews"]
    short = bursts.span_days < cfg["short_span_days"] and total is not None and total < cfg["short_span_max_total"]
    return {"young": bool(few or short), "total_reviews": total, "sample_span_days": bursts.span_days}

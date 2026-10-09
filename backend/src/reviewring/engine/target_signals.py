"""Target-level signals T1-T5 (spec 9.2). Free: they use the target's reviews only."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
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


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def span_text(minutes: float) -> str:
    """'89 minutes', '18 hours', '3 days': how long a burst took, in the unit a reader would use."""
    if minutes < 120:
        n = max(1, round(minutes))
        return f"{n} minute{'s' if n != 1 else ''}"
    if minutes < 48 * 60:
        return f"{round(minutes / 60)} hours"
    return f"{round(minutes / 1440)} days"


def pace_text(per_day: float) -> str:
    """'about 3 reviews a day', 'about one review a week', 'about one review every 10 days'."""
    if per_day >= 1.5:
        return f"about {round(per_day)} reviews a day"
    if per_day >= 0.9:
        return "about one review a day"
    per_week = per_day * 7
    if per_week >= 1.5:
        return f"about {round(per_week)} reviews a week"
    if per_week >= 0.9:
        return "about one review a week"
    return f"about one review every {round(1 / per_day)} days" if per_day > 0 else "almost no reviews"


def review_bursts(reviews: list[TargetReview]) -> dict[str, Any]:
    """Bursts of same-star reviews: what a business buying praise (5★) or someone attacking it (1★) produces.

    For each of 5★ and 1★: the stretch of at most ``max_span_hours`` holding the most reviews of that rating. It
    is flagged when it holds at least ``min_share`` of the reviews examined (and ``min_count``), and arrives at least
    ``min_pace`` times faster than the listing's other reviews. Only reviews of that rating count, and the
    account behind each review doesn't decide anything (first-time accounts are reported, not required). Exact
    timestamps are used, so "43 reviews in 89 minutes" is told as that, not as a 3-day window.
    """
    cfg = config.load_tunables()["review_burst"]
    dated = sorted((r for r in reviews if r.posted_at is not None), key=lambda r: _utc(r.posted_at))  # type: ignore[arg-type]
    n = len(dated)
    out: dict[str, Any] = {"examined": n, "clusters": []}
    if n < int(cfg["min_count"]):
        return out
    first, last = _utc(dated[0].posted_at), _utc(dated[-1].posted_at)  # type: ignore[arg-type]
    span_days = max((last - first).total_seconds() / 86400, 1.0)
    out["pace_per_day"] = round(n / span_days, 4)
    window = timedelta(hours=float(cfg["max_span_hours"]))
    need = max(int(cfg["min_count"]), cfg["min_share"] * n)
    max_first = int(config.tunable("single_use", "max_reviews"))
    for stars, direction in ((5, "positive"), (1, "negative")):
        pool = [r for r in dated if r.rating == stars]
        for _ in range(int(cfg["max_rounds"])):
            if len(pool) < int(cfg["min_count"]):
                break
            times = [_utc(r.posted_at) for r in pool]  # type: ignore[arg-type]
            best_i, best_j, j = 0, 0, 0
            for i in range(len(times)):
                while j + 1 < len(times) and times[j + 1] - times[i] <= window:
                    j += 1
                if j - i > best_j - best_i:
                    best_i, best_j = i, j
            # A review cut off from the rest by a long gap belongs to the listing's ordinary flow, not the burst.
            gap = timedelta(hours=float(cfg["max_gap_hours"]))
            while best_j > best_i and times[best_j] - times[best_j - 1] > gap:
                best_j -= 1
            while best_i < best_j and times[best_i + 1] - times[best_i] > gap:
                best_i += 1
            members = pool[best_i : best_j + 1]
            start, end = times[best_i], times[best_j]
            minutes = (end - start).total_seconds() / 60
            # The usual pace, from every other review in the sample; a burst is measured over at least a day.
            others = n - len(members)
            other_days = max(span_days - minutes / 1440, 1.0)
            usual = others / other_days
            pace = (len(members) / max(minutes / 1440, 1.0)) / usual if usual > 0 else None
            k = min(len(members), max(2, math.ceil(len(members) * float(cfg["core_share"]))))
            core = min(
                ((times[best_i + a + k - 1] - times[best_i + a], a) for a in range(len(members) - k + 1)),
                default=(end - start, 0),
            )
            flagged = (
                len(members) >= need
                and others >= int(cfg["min_others"])
                and pace is not None
                and pace >= float(cfg["min_pace"])
            )
            out["clusters"].append(
                {
                    "direction": direction,
                    "stars": stars,
                    "count": len(members),
                    "share": round(len(members) / n, 3),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "minutes": round(minutes, 1),
                    "core": {
                        "count": k,
                        "minutes": round(core[0].total_seconds() / 60, 1),
                        "start": times[best_i + core[1]].isoformat(),
                        "end": times[best_i + core[1] + k - 1].isoformat(),
                    },
                    "usual_per_day": round(usual, 4),
                    "pace": round(pace, 1) if pace is not None else None,
                    # Minutes after the start, one per review: enough to draw the burst, with no timestamps.
                    "offsets": [round((t - start).total_seconds() / 60, 1) for t in times[best_i : best_j + 1]],
                    "first_time": sum(
                        1 for r in members if r.reviewer_reviews is not None and r.reviewer_reviews <= max_first
                    ),
                    "flagged": flagged,
                    "review_ids": sorted(r.review_id for r in members),
                }
            )
            if not flagged:
                break
            taken = {r.review_id for r in members}
            pool = [r for r in pool if r.review_id not in taken]
    return out


def generated_marker(review: TargetReview) -> str | None:
    """The first chatbot-reply or placeholder phrase in the text (or the one a fixture kept)."""
    if review.text:
        low = " ".join(review.text.casefold().split())
        for m in config.load_tunables()["generated_text"]["markers"]:
            if m in low:
                return m
        return None
    return review.generated_marker


EXCERPT_CHARS = 240


def generated_excerpt(review: TargetReview) -> str | None:
    """The review's text around its chatbot or placeholder phrase, whitespace-normalized and at most ~240 chars."""
    marker = generated_marker(review)
    if not marker or not review.text:
        return None
    text = " ".join(review.text.split())
    if len(text) <= EXCERPT_CHARS:
        return text
    at = max(0, text.casefold().find(marker))
    start = max(0, at - 80)
    end = min(len(text), start + EXCERPT_CHARS)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def rating_gap(inp: AnalysisInput) -> dict[str, Any]:
    """Displayed rating vs the newest reviews, and what the rest must average for the display to hold."""
    cfg = config.load_tunables()["rating_gap"]
    rated = [r.rating for r in inp.target_reviews if r.rating is not None]
    displayed, total = inp.target.rating, inp.target.total_reviews
    if not rated or displayed is None or not total or total <= len(rated):
        return {"available": False}
    recent = sum(rated) / len(rated)
    older = (displayed * total - sum(rated)) / (total - len(rated))
    gap = displayed - recent
    return {
        "available": True,
        "displayed": displayed,
        "total": total,
        "recent_mean": round(recent, 2),
        "recent_count": len(rated),
        "older_count": total - len(rated),
        "older_implied_mean": round(min(5.0, older), 2),
        "gap": round(gap, 2),
        "flagged": gap >= cfg["min_gap"] and total >= cfg["min_total_ratio"] * len(rated),
    }


def top_rated_sample(inp: AnalysisInput) -> dict[str, Any]:
    """Who wrote the highest-rated reviews, and when: the busiest window, single-use share, generated text."""
    sample = inp.top_rated
    if not sample:
        return {"available": False}
    months = int(config.tunable("rating_gap", "cluster_months"))
    max_single = int(config.tunable("single_use", "max_reviews"))
    dated = sorted(r.posted_at for r in sample if r.posted_at)
    best = (0, None, None)
    for i, start in enumerate(dated):
        end_limit = start + timedelta(days=30 * months)
        n = sum(1 for d in dated[i:] if d <= end_limit)
        if n > best[0]:
            best = (n, start, max(d for d in dated[i:] if d <= end_limit))
    known = [r for r in sample if r.reviewer_reviews is not None]
    single = [r for r in known if r.reviewer_reviews <= max_single]
    markers = []
    for r in sample:
        m = generated_marker(r)
        if m:
            markers.append(
                {
                    "review_id": r.review_id,
                    "rating": r.rating,
                    "day": ist_date(r.posted_at).isoformat() if r.posted_at else None,
                    "marker": m,
                    "excerpt": generated_excerpt(r),
                    "reviewer_reviews": r.reviewer_reviews,
                }
            )
    return {
        "available": True,
        "count": len(sample),
        "window_months": months,
        "window_count": best[0],
        "window_start": ist_date(best[1]).isoformat() if best[1] else None,
        "window_end": ist_date(best[2]).isoformat() if best[2] else None,
        "window_share": round(best[0] / len(sample), 3) if sample else 0.0,
        "single_use_share": round(len(single) / len(known), 3) if known else None,
        "no_photo_share": round(sum(1 for r in sample if r.reviewer_photos == 0) / len(sample), 3),
        "generated": markers,
    }

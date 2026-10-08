"""Per-review warning signs and the sieve that sorts the newest reviews by them.

Most bought reviews in the real data came from cheap first-time accounts, not organised rings, and a single review
from a first-time account looks exactly like a real customer's. So each review gets every sign that applies,
strongest first, and the reader decides which to set aside. A review is drawn in the first branch that is set
aside; the rest are the reviews "worth reading". Nothing here calls a review fake.

Strengths:
- strong: near-certain to be inauthentic text or behaviour (chatbot text, copied text, a burst of first-time
  accounts, a linked reviewer group). Set aside by default.
- opinion: an AI model's reading of the text. Shown with its quoted cues, kept by default.
- context: true of many real customers too. Kept by default.
"""

from __future__ import annotations

import statistics
from typing import Any

from .. import config
from ..model import TargetReview

SIGNS: dict[str, dict[str, str]] = {
    "chatbot_text": {
        "name": "Chatbot or template text",
        "short": "Chatbot text",
        "strength": "strong",
        "explain": "Contains a phrase only a chatbot or an unfilled template produces, such as "
        "“I'm unable to generate a review” or “[Hotel Name]”.",
    },
    "copied_text": {
        "name": "Copied text",
        "short": "Copied text",
        "strength": "strong",
        "explain": "Near-identical to a review that another account wrote.",
    },
    "voice_mismatch": {
        "name": "Not in the reviewer's own voice",
        "short": "Not their own voice",
        "strength": "strong",
        "explain": "The reviewer's other reviews are written very differently. An AI model compared them and quotes "
        "the difference; both are shown side by side. Typical of scripted or incentivised reviews posted from real "
        "accounts.",
    },
    "keyword_style": {
        "name": "Written like a search ad",
        "short": "Search-ad phrasing",
        "strength": "strong",
        "explain": "Names the business or its category together with its neighbourhood or city, the way search ads are "
        "written (\u201cpackers and movers in [area], [city]\u201d), as several accounts here do.",
    },
    "first_time_burst": {
        "name": "First-time accounts in a burst",
        "short": "Burst of first-time accounts",
        "strength": "strong",
        "explain": "Posted in a sudden burst of reviews that came mostly from accounts that have reviewed "
        "nothing else.",
    },
    "linked_group": {
        "name": "Linked reviewer group",
        "short": "Linked group",
        "strength": "strong",
        "explain": "The reviewer belongs to a group of accounts that reviewed the same unrelated businesses in "
        "distant cities.",
    },
    "ai_style": {
        "name": "Reads as AI-written",
        "short": "Reads as AI-written",
        "strength": "opinion",
        "explain": "An AI model thinks this reads as written by a chatbot, and quotes the phrases why. That's an "
        "opinion, not proof: real customers also polish honest reviews with AI.",
    },
    "review_spree": {
        "name": "Reviewing spree",
        "short": "Reviewing spree",
        "strength": "context",
        "explain": "The reviewer rated many unrelated businesses in several cities within a month, nearly all "
        "5★: the shape of “rate and earn” tasks, though some travellers review this way too.",
    },
    "first_time_account": {
        "name": "First-time account",
        "short": "First-time account",
        "strength": "context",
        "explain": "The account shows no other reviews. Many real customers create an account just to leave one "
        "review, so this alone isn't a warning sign.",
    },
}


def order() -> list[str]:
    return [k for k in config.tunable("signs", "order") if k in SIGNS]


def default_set_aside() -> list[str]:
    return [k for k in config.tunable("signs", "set_aside_by_default") if k in SIGNS]


def is_first_time(reviewer_reviews: int | None) -> bool:
    return reviewer_reviews is not None and reviewer_reviews <= int(config.tunable("signs", "first_time_max_reviews"))


def review_signs(
    review: TargetReview,
    *,
    marker: str | None,
    copied: bool,
    in_first_time_burst: bool,
    label: str,
    judgement: dict[str, Any] | None,
    spree: bool,
    keyword: bool = False,
    voice: dict[str, Any] | None = None,
) -> list[str]:
    """Every sign that applies to one review, in sieve order."""
    found = {
        "chatbot_text": bool(marker),
        "copied_text": copied,
        "voice_mismatch": bool(voice and voice.get("verdict") == "different_voice"),
        "keyword_style": keyword,
        "first_time_burst": in_first_time_burst,
        "linked_group": label in ("ring", "possible_ring_trip"),
        "ai_style": bool(judgement and judgement.get("verdict") == "ai_style"),
        "review_spree": spree,
        "first_time_account": is_first_time(review.reviewer_reviews),
    }
    return [k for k in order() if found.get(k)]


def _mean(values: list[int]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def sieve_summary(rows: list[dict[str, Any]], ai: dict[str, Any]) -> dict[str, Any]:
    """Counts and mean ratings per sign, and the reviews kept when the default signs are set aside."""
    keys = order()
    aside = set(default_set_aside())
    signs = {}
    for k in keys:
        having = [r for r in rows if k in r["signs"]]
        signs[k] = {
            **SIGNS[k],
            "count": len(having),
            "mean": _mean([r["rating"] for r in having if r["rating"] is not None]),
            "set_aside_by_default": k in aside,
        }
    kept = [r for r in rows if not aside.intersection(r["signs"])]
    clear = [r for r in rows if not r["signs"]]
    return {
        "order": keys,
        "set_aside_by_default": [k for k in keys if k in aside],
        "signs": signs,
        "examined": len(rows),
        "kept": {"count": len(kept), "mean": _mean([r["rating"] for r in kept if r["rating"] is not None])},
        "no_signs": {"count": len(clear), "mean": _mean([r["rating"] for r in clear if r["rating"] is not None])},
        "all": {"count": len(rows), "mean": _mean([r["rating"] for r in rows if r["rating"] is not None])},
        "ai": ai,
    }


def ai_coverage(reviews: list[TargetReview], judgements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """How many reviews the AI-text opinion covered, and why the rest weren't judged."""
    min_words = int(config.tunable("ai_text", "min_words"))
    eligible = [r for r in reviews if r.review_id in judgements or (r.text and len(r.text.split()) >= min_words)]
    judged = [judgements[r.review_id] for r in reviews if r.review_id in judgements]
    with_text = sum(1 for r in reviews if r.text or r.review_id in judgements)
    verdicts = [j.get("verdict") for j in judged]
    models = sorted({str(j.get("model")) for j in judged if j.get("model")})
    return {
        "min_words": min_words,
        "eligible": len(eligible),
        "judged": len(judged),
        "too_short": max(0, with_text - len(eligible)),
        "no_text": len(reviews) - with_text,
        "ai_style": verdicts.count("ai_style"),
        "human_style": verdicts.count("human_style"),
        "unclear": verdicts.count("unclear"),
        "model": models[0] if models else None,
    }


def first_time_skew(reviews: list[TargetReview]) -> dict[str, Any]:
    """Are 5-star reviews much more likely to come from first-time accounts than the other reviews?

    The singleton-review insight (Xie et al., KDD 2012): most reviewers write one review, and on their own they're
    harmless. Bought ones show up as first-time accounts concentrated where the rating is pushed up.
    """
    cfg = config.load_tunables()["signs"]
    known = [r for r in reviews if r.reviewer_reviews is not None and r.rating is not None]
    five = [r for r in known if r.rating == 5]
    other = [r for r in known if r.rating is not None and r.rating < 5]
    f5 = sum(1 for r in five if is_first_time(r.reviewer_reviews))
    fo = sum(1 for r in other if is_first_time(r.reviewer_reviews))
    if not five or not other:
        return {"available": False, "five_star": len(five), "other": len(other)}
    share5, share_o = f5 / len(five), fo / len(other)
    ratio = share5 / max(share_o, 0.5 / len(other))  # half a review instead of zero, so the ratio stays finite
    flagged = (
        len(five) >= cfg["skew_min_five_star"]
        and len(other) >= cfg["skew_min_other"]
        and ratio >= cfg["skew_min_ratio"]
        and share5 >= cfg["skew_min_share"]
        and f5 >= 5
    )
    return {
        "available": True,
        "five_star": len(five),
        "five_star_first_time": f5,
        "other": len(other),
        "other_first_time": fo,
        "ratio": round(ratio, 1),
        "flagged": flagged,
    }


def voice_coverage(inp_voice: dict[str, dict[str, Any]], eligible: int) -> dict[str, Any]:
    """How many checked reviewers' writing was compared, and how many reviews were not in their author's voice."""
    verdicts = [v.get("verdict") for v in inp_voice.values()]
    models = sorted({str(v.get("model")) for v in inp_voice.values() if v.get("model")})
    return {
        "eligible": eligible,
        "compared": len(verdicts),
        "different_voice": verdicts.count("different_voice"),
        "same_voice": verdicts.count("same_voice"),
        "unclear": verdicts.count("unclear"),
        "model": models[0] if models else None,
    }

"""Reviews written like search ads: the business or its category named together with its neighbourhood or city.

Real customers write "the team" or "they"; review writers paid for search ranking write the search phrase:
"packers and movers in [area], [city]", "[name] Packers and Movers [area] Delhi", "if you're looking for packers and
movers delhi". On real listings this phrasing appeared in 16-21 of 44 reviews where the rest of the evidence was
strong, and in 0-7 elsewhere (docs/research-2026-10-08.md). One customer writing it means nothing, so a review only
carries the sign when several accounts at the listing do it.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from ..model import Place, TargetReview

CONNECT = {"in", "at", "of", "and", "n", "&", "the"}
NOT_NAME = {"pvt", "ltd", "private", "limited", "the", "and", "co", "company", "india", "llp", "inc"}
NOT_PLACE = {
    "shop",
    "no",
    "road",
    "rd",
    "street",
    "st",
    "near",
    "opp",
    "opposite",
    "floor",
    "main",
    "cross",
    "sector",
    "phase",
    "block",
    "plot",
    "building",
    "tower",
    "flat",
    "house",
    "lane",
    "marg",
    "behind",
    "beside",
    "next",
    "ground",
    "first",
    "second",
    "third",
    "office",
    "complex",
    "india",
    "stage",
    "layout",
    "nagar",
    "colony",
    "new",
    "old",
    "greater",
    "navi",
    "east",
    "west",
    "north",
    "south",
    "central",
    "city",
    "town",
}
_BREAK = re.compile(r"[.!?\n]+")
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for i, part in enumerate(_BREAK.split(text.casefold())):
        if i:
            out.append("|")  # sentence break: a phrase never runs across it
        out.extend(_TOKEN.findall(part))
    return out


def name_tokens(place: Place) -> set[str]:
    return {t for t in _TOKEN.findall((place.title or "").casefold()) if len(t) >= 2 and t not in NOT_NAME}


def place_tokens(place: Place) -> set[str]:
    """The listing's neighbourhood, city, metro aliases and state, minus anything that is part of its own name."""
    geo = config.load_tunables()["geo"]
    words = set(_TOKEN.findall((place.address or "").casefold())) | set(_TOKEN.findall((place.area or "").casefold()))
    for canonical, *members in geo["metros"]:
        names = [canonical, *members]
        if any(
            n.casefold() in (place.area or "").casefold() or n.casefold() in (place.address or "").casefold()
            for n in names
        ):
            for n in names:
                words |= set(_TOKEN.findall(n.casefold()))
    words = {w for w in words if len(w) >= 3 and not w.isdigit() and w not in NOT_PLACE and w != "ncr"}
    return words - name_tokens(place)


def keyword_phrase(text: str | None, names: set[str], places: set[str]) -> str | None:
    """The first "name or category, then place" phrase in the text, e.g. "packers and movers in hadapsar pune"."""
    if not text or not names or not places:
        return None
    toks = _tokens(text)
    for i, tok in enumerate(toks):
        if tok not in names:
            continue
        for j in range(i + 1, min(len(toks), i + 6)):
            t = toks[j]
            if t in places:
                end = j
                while end + 1 < len(toks) and toks[end + 1] in places:
                    end += 1
                return " ".join(toks[i : end + 1])
            if t not in names and t not in CONNECT:
                break
    return None


def keyword_style(reviews: list[TargetReview], target: Place) -> dict[str, Any]:
    """Which reviews read like search ads, and whether enough accounts do it for it to count."""
    cfg = config.load_tunables()["keyword_style"]
    names, places = name_tokens(target), place_tokens(target)
    hits: dict[str, str] = {}
    for r in reviews:
        phrase = keyword_phrase(r.text, names, places)
        if phrase:
            hits[r.review_id] = phrase
    accounts = {r.contributor_id or r.review_id for r in reviews if r.review_id in hits}
    with_text = sum(1 for r in reviews if r.text and r.text.strip())
    need = max(int(cfg["min_accounts"]), cfg["min_share"] * with_text)
    flagged = len(accounts) >= need
    phrases: dict[str, int] = {}
    for p in hits.values():
        phrases[p] = phrases.get(p, 0) + 1
    return {
        "flagged": flagged,
        "accounts": len(accounts),
        "with_text": with_text,
        "needed": round(need, 1),
        "review_ids": sorted(hits) if flagged else [],
        "phrases": dict(sorted(phrases.items(), key=lambda kv: -kv[1])[:6]),
        "hits": hits,
    }

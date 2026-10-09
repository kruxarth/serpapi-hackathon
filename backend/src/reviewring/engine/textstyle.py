"""Reviews written like search ads: the category, or the name again and again, with its neighbourhood or city.

Real customers write "the team" or "they"; review writers paid for search ranking write the search phrase:
"best packers and movers in [area]", "packing and moving services in [area], [city]". On real listings this phrasing
appeared in 16-21 of 44 reviews where the rest of the evidence was strong, and in 0-7 elsewhere
(docs/research-2026-10-08.md).

Naming the business with its area once ("Om Sai Packers and Movers, Hadapsar") is how many customers refer to it, so
that alone is only context. A review reads like an ad when its phrase is the bare category with a place ("packers and
movers in wakad", no name in it) or it names the business with a place more than once. Either way, one customer
writing it means nothing: the listing must show it from several accounts first.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from ..model import Place, TargetReview

CONNECT = {"in", "at", "of", "and", "n", "&", "the"}
# Category words: a phrase made only of these (and a place) is the bare search term, not the business's name.
GENERIC = {
    "packers", "movers", "packer", "mover", "packing", "moving", "shifting", "relocation", "logistics", "cargo",
    "transport", "transportation", "travels", "tours", "hotel", "hotels", "resort", "restaurant", "cafe", "clinic",
    "dental", "dentist", "hospital", "salon", "spa", "gym", "lodge", "hostel", "inn", "pg", "service", "services",
}  # fmt: skip
INSIDE = {"service", "services", "company", "companies"}  # may sit inside a phrase but never start one
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
    "park",
}
_BREAK = re.compile(r"[.!?\n]+")
_TOKEN = re.compile(r"[a-z0-9]+")


_POSSESSIVE = re.compile(r"['\u2019]s\b")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for i, part in enumerate(_BREAK.split(_POSSESSIVE.sub("", text.casefold()))):
        if i:
            out.append("|")  # sentence break: a phrase never runs across it
        out.extend(_TOKEN.findall(part))
    return out


def name_tokens(place: Place) -> set[str]:
    return {t for t in _TOKEN.findall((place.title or "").casefold()) if len(t) >= 2 and t not in NOT_NAME}


def start_tokens(place: Place) -> set[str]:
    """Words a search phrase starts with: the business's name and its type ("Moving service" -> moving)."""
    kind = {t for t in _TOKEN.findall((place.type or "").casefold()) if len(t) >= 3}
    return name_tokens(place) | (kind - INSIDE)


def brand_tokens(place: Place) -> set[str]:
    """The distinctive part of the name ("om", "sai"); a phrase without any of them is the bare category."""
    return name_tokens(place) - GENERIC


def place_tokens(place: Place) -> set[str]:
    """The listing's neighbourhood, city, metro aliases and state, minus anything that is part of its own name.

    Only the end of the address counts ("..., Hadapsar, Pune, Maharashtra 411028"): its start names buildings and
    landmarks ("Polaris Society", "Fire Station") that would match ordinary words.
    """
    geo = config.load_tunables()["geo"]
    parts = [part.strip() for part in (place.address or "").split(",") if part.strip()]
    parts = [part for part in parts if part.casefold() != "india" and not part.replace(" ", "").isdigit()]
    tail = " ".join(parts[-4:])  # e.g. "Wakad, Pimpri-Chinchwad, Pune, Maharashtra 411057"
    words = set(_TOKEN.findall(tail.casefold())) | set(_TOKEN.findall((place.area or "").casefold()))
    for canonical, *members in geo["metros"]:
        names = [canonical, *members]
        if any(
            n.casefold() in (place.area or "").casefold() or n.casefold() in (place.address or "").casefold()
            for n in names
        ):
            for n in names:
                words |= set(_TOKEN.findall(n.casefold()))
    words = {w for w in words if len(w) >= 3 and w.isalpha() and w not in NOT_PLACE and w != "ncr"}
    return words - name_tokens(place)


def locality_tokens(place: Place) -> set[str]:
    """The place words below the city ("hadapsar", "maharashtra"): presentation mode hides them, the city stays."""
    return place_tokens(place) - set(_TOKEN.findall((place.area or "").casefold()))


def keyword_phrases(text: str | None, starts: set[str], places: set[str]) -> list[str]:
    """Every "name or category, then place" phrase in the text, e.g. "packers and movers in hadapsar pune"."""
    if not text or not starts or not places:
        return []
    toks = _tokens(text)
    out: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i] not in starts:
            i += 1
            continue
        end = None
        for j in range(i + 1, min(len(toks), i + 7)):
            t = toks[j]
            if t in places:
                end = j
                while end + 1 < len(toks) and toks[end + 1] in places:
                    end += 1
                break
            if t not in starts and t not in CONNECT and t not in INSIDE:
                break
        if end is None:
            i += 1
            continue
        out.append(" ".join(toks[i : end + 1]))
        i = end + 1
    return out


def keyword_phrase(text: str | None, names: set[str], places: set[str]) -> str | None:
    """The first such phrase, or None."""
    found = keyword_phrases(text, names, places)
    return found[0] if found else None


def keyword_style(reviews: list[TargetReview], target: Place) -> dict[str, Any]:
    """Which reviews read like search ads, which only name the business with its area, and whether enough accounts
    at the listing write this way for either to count."""
    cfg = config.load_tunables()["keyword_style"]
    starts, brand, places = start_tokens(target), brand_tokens(target), place_tokens(target)
    hits: dict[str, str] = {}
    ads: set[str] = set()
    for r in reviews:
        found = keyword_phrases(r.text, starts, places)
        if not found:
            continue
        bare = [p for p in found if not set(p.split()) & brand]
        hits[r.review_id] = (bare or found)[0]
        if bare or len(found) >= 2:
            ads.add(r.review_id)
    accounts = {r.contributor_id or r.review_id for r in reviews if r.review_id in hits}
    with_text = sum(1 for r in reviews if r.text and r.text.strip())
    need = max(int(cfg["min_accounts"]), cfg["min_share"] * with_text)
    flagged = len(accounts) >= need
    phrases: dict[str, int] = {}
    for rid in sorted(ads) or sorted(hits):
        phrases[hits[rid]] = phrases.get(hits[rid], 0) + 1
    return {
        "flagged": flagged,
        "accounts": len(accounts),
        "with_text": with_text,
        "needed": round(need, 1),
        "ads": len(ads),
        "review_ids": sorted(ads) if flagged else [],
        "named_ids": sorted(set(hits) - ads) if flagged else [],
        "phrases": dict(sorted(phrases.items(), key=lambda kv: -kv[1])[:6]),
        "hits": hits,
    }

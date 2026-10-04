"""Canonical SerpApi request definitions.

FROZEN at M1: the probe's cached responses must be reused by later collection,
so the parameters and their canonical form must never change. The request key
is SHA-256 over the sorted parameters (engine included, API key excluded).
``tests/test_requests.py`` pins the exact keys.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

REVIEWS_ENGINE = "google_maps_reviews"
CONTRIBUTOR_ENGINE = "google_maps_contributor_reviews"
MAPS_ENGINE = "google_maps"

# Fixed by SerpApi and frozen in the request keys; deliberately not tunable.
FIRST_PAGE_SIZE = 8  # page 1 always returns 8 and doesn't accept num
PAGE_SIZE = 20  # num for later review pages
HISTORY_NUM = 200  # contributor reviews per call (the maximum)


@dataclass(frozen=True)
class SerpRequest:
    engine: str
    params: dict[str, str] = field(hash=False)
    label: str = field(default="", compare=False, hash=False)

    def all_params(self) -> dict[str, str]:
        return {"engine": self.engine, **self.params}

    def canonical(self) -> str:
        return json.dumps(self.all_params(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def key(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


def _s(value: object) -> str:
    return str(value)


def reviews_page(data_id: str, next_page_token: str | None = None) -> SerpRequest:
    """One page of a place's reviews, newest first. Page 1 is 8 reviews and takes no ``num``."""
    params = {"data_id": data_id.strip().lower(), "hl": "en", "sort_by": "newestFirst"}
    label = "reviews page 1"
    if next_page_token:
        params["next_page_token"] = next_page_token
        params["num"] = str(PAGE_SIZE)
        label = "reviews page"
    return SerpRequest(REVIEWS_ENGINE, params, label)


def top_rated_page(data_id: str, next_page_token: str | None = None) -> SerpRequest:
    """Highest-rated reviews first: where a high displayed rating actually comes from."""
    params = {"data_id": data_id.strip().lower(), "hl": "en", "sort_by": "ratingHigh"}
    if next_page_token:
        params["next_page_token"] = next_page_token
        params["num"] = str(PAGE_SIZE)
    return SerpRequest(REVIEWS_ENGINE, params, "highest-rated reviews page")


def contributor_history(contributor_id: str) -> SerpRequest:
    params = {
        "contributor_id": _s(contributor_id).strip(),
        "hl": "en",
        "num": str(HISTORY_NUM),
    }
    return SerpRequest(CONTRIBUTOR_ENGINE, params, "reviewer history")


def place_by_cid(data_cid: str | int) -> SerpRequest:
    return SerpRequest(MAPS_ENGINE, {"data_cid": _s(data_cid), "hl": "en"}, "place lookup (cid)")


def place_by_place_id(place_id: str) -> SerpRequest:
    return SerpRequest(MAPS_ENGINE, {"place_id": place_id.strip(), "hl": "en"}, "place lookup (place_id)")


def place_search(query: str) -> SerpRequest:
    q = " ".join(query.split())
    return SerpRequest(MAPS_ENGINE, {"q": q, "type": "search", "hl": "en"}, "place search")


def data_cid_from_data_id(data_id: str) -> str:
    """The decimal form of the second hexadecimal half of a data_id (spec 4.3)."""
    second = data_id.strip().lower().split(":")[1]
    return str(int(second, 16))

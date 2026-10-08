"""In-memory inputs to the analysis engine.

The engine is a pure function of an :class:`AnalysisInput` plus the tunables.
Collection builds one from the cache; demo mode and the evaluation harness
build one from fixtures, so all three share exactly the same code path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .normalize.text import TextFeatures


def place_key_for(data_id: str | None, title: str | None = None, address: str | None = None) -> str:
    if data_id:
        return data_id.strip().lower()
    basis = f"{' '.join((title or '').lower().split())}|{' '.join((address or '').lower().split())}"
    return "h:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


@dataclass
class Place:
    place_key: str
    data_id: str | None = None
    title: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    type: str | None = None
    area: str | None = None
    rating: float | None = None
    total_reviews: int | None = None

    def merge(self, other: Place) -> None:
        """Fill missing fields from another sighting of the same place."""
        for name in ("data_id", "title", "address", "lat", "lng", "type", "area", "rating", "total_reviews"):
            if getattr(self, name) is None and getattr(other, name) is not None:
                setattr(self, name, getattr(other, name))


@dataclass
class TargetReview:
    review_id: str
    contributor_id: str | None
    rating: int | None
    posted_at: datetime | None  # exact, from iso_date
    edited: bool = False
    text: str | None = None  # None when a fixture dropped it
    has_images: bool = False
    reviewer_reviews: int | None = None  # None = unknown, never 0 by default
    reviewer_photos: int | None = None
    local_guide: bool | None = None
    reviewer_name: str | None = None
    generated_marker: str | None = None  # kept by fixtures, which drop most texts


@dataclass
class HistoryReview:
    contributor_id: str
    review_id: str
    place_key: str | None
    rating: int | None
    relative_date: str | None
    date_min: date | None
    date_max: date | None
    edited: bool = False
    image_dates: list[str] = field(default_factory=list)
    text: str | None = None
    travel_group: str | None = None  # from hotel review details ("family", "friends", "business", ...)

    @property
    def precision_days(self) -> int | None:
        if self.date_min is None or self.date_max is None:
            return None
        return (self.date_max - self.date_min).days


@dataclass
class Contributor:
    contributor_id: str
    name: str | None = None
    level: int | None = None
    points: int | None = None
    local_guide: bool | None = None
    contributions: dict[str, Any] = field(default_factory=dict)
    reviews_returned: int = 0
    truncated: bool = False
    status: str = "ok"  # ok | empty | private | error
    fetched_at: datetime | None = None

    @property
    def total_reviews(self) -> int | None:
        value = self.contributions.get("reviews")
        return value if isinstance(value, int) else None

    @property
    def total_photos(self) -> int | None:
        value = self.contributions.get("photos")
        return value if isinstance(value, int) else None


@dataclass
class Expansion:
    contributor_id: str
    round: int  # 1 or 2
    reason: str  # priority | baseline


@dataclass
class AnalysisInput:
    target: Place
    target_reviews: list[TargetReview]
    places: dict[str, Place]
    contributors: dict[str, Contributor]
    histories: dict[str, list[HistoryReview]]
    expansions: list[Expansion]
    fetched_at: datetime
    params: dict[str, Any] = field(default_factory=dict)
    # Precomputed text features by text_id. Fixtures carry these because they drop most texts.
    text_features: dict[str, TextFeatures] | None = None
    notes: list[str] = field(default_factory=list)
    # A sample of the highest-rated reviews, fetched only when the displayed rating far exceeds recent ones.
    top_rated: list[TargetReview] = field(default_factory=list)
    # An AI model's opinion of each long-enough review text, by review_id: {"verdict": "ai_style" | "human_style" |
    # "unclear", "cues": [phrases quoted from the text]}. Never decides anything; fixtures carry it.
    text_judgements: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Is a checked reviewer's review of this business in their own voice? By contributor_id: {"verdict":
    # "different_voice" | "same_voice" | "unclear", "here": a phrase from it, "elsewhere": one from their others}.
    voice_judgements: dict[str, dict[str, Any]] = field(default_factory=dict)

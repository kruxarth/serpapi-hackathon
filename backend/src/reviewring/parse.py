"""Parse cached SerpApi bodies into model objects (spec 4.1, 4.2).

Parsers only ever read responses the gateway already stored (Rule 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .model import Contributor, HistoryReview, Place, TargetReview, place_key_for
from .normalize.dates import absolute_range, parse_iso
from .normalize.geo import area_from_address
from .normalize.text import review_text


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = value.replace(",", "").strip()
        return int(digits) if digits.isdigit() else None
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _gps(info: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = info.get("gps_coordinates") or {}
    return _float(gps.get("latitude")), _float(gps.get("longitude"))


def place_from_info(info: dict[str, Any], data_id: str | None = None) -> Place:
    data_id = (info.get("data_id") or data_id or None) and str(info.get("data_id") or data_id).lower()
    lat, lng = _gps(info)
    address = info.get("address")
    return Place(
        place_key=place_key_for(data_id, info.get("title"), address),
        data_id=data_id,
        title=info.get("title"),
        address=address,
        lat=lat,
        lng=lng,
        type=info.get("type"),
        area=area_from_address(address),
        rating=_float(info.get("rating")),
        total_reviews=_int(info.get("reviews")),
    )


def target_place(body: dict[str, Any], data_id: str) -> Place:
    return place_from_info(body.get("place_info") or {}, data_id)


def target_reviews(body: dict[str, Any]) -> list[TargetReview]:
    out = []
    for r in body.get("reviews") or []:
        if not isinstance(r, dict) or not r.get("review_id"):
            continue
        user = r.get("user") or {}
        cid = user.get("contributor_id")
        date_text = str(r.get("date") or "")
        out.append(
            TargetReview(
                review_id=str(r["review_id"]),
                contributor_id=str(cid) if cid else None,
                rating=_int(r.get("rating")),
                posted_at=parse_iso(r.get("iso_date")),
                edited=bool(r.get("iso_date_of_last_edit")) or date_text.lower().startswith("edited"),
                text=review_text(r),
                has_images=bool(r.get("images")),
                reviewer_reviews=_int(user.get("reviews")),
                reviewer_photos=_int(user.get("photos")),
                local_guide=user.get("local_guide") if isinstance(user.get("local_guide"), bool) else None,
                reviewer_name=user.get("name"),
            )
        )
    return out


def contributor_history(
    body: dict[str, Any], contributor_id: str, fetched_at: datetime, status: str = "ok"
) -> tuple[Contributor, list[HistoryReview], list[Place]]:
    """A reviewer's profile, visible reviews and the places they reviewed."""
    info = body.get("contributor") or {}
    reviews = [r for r in body.get("reviews") or [] if isinstance(r, dict)]
    contributions = info.get("contributions") if isinstance(info.get("contributions"), dict) else {}
    contributions = {k: _int(v) if _int(v) is not None else v for k, v in contributions.items()}
    total = contributions.get("reviews")
    if status == "empty" or not reviews:
        fetch_status = "empty" if (status == "empty" or not info) else "private"
    else:
        fetch_status = "ok"
    contributor = Contributor(
        contributor_id=contributor_id,
        name=info.get("name"),
        level=_int(info.get("level")),
        points=_int(info.get("points")),
        local_guide=info.get("local_guide") if isinstance(info.get("local_guide"), bool) else None,
        contributions=contributions,
        reviews_returned=len(reviews),
        truncated=isinstance(total, int) and total > len(reviews),
        status=fetch_status,
        fetched_at=fetched_at,
    )
    history: list[HistoryReview] = []
    places: list[Place] = []
    for i, r in enumerate(reviews):
        place_info = r.get("place_info") or {}
        place = place_from_info(place_info) if place_info else None
        if place is not None and (place.title or place.data_id):
            places.append(place)
        image_dates = [
            str(img.get("date")) for img in r.get("images") or [] if isinstance(img, dict) and img.get("date")
        ]
        rng = absolute_range(r.get("date"), fetched_at, image_dates)
        history.append(
            HistoryReview(
                contributor_id=contributor_id,
                review_id=str(r.get("review_id") or f"{contributor_id}#{i}"),
                place_key=place.place_key if place is not None and (place.title or place.data_id) else None,
                rating=_int(r.get("rating")),
                relative_date=r.get("date"),
                date_min=rng.date_min,
                date_max=rng.date_max,
                edited=rng.edited,
                image_dates=image_dates,
                text=review_text(r),
            )
        )
    return contributor, history, places


def lookup_place(body: dict[str, Any]) -> Place | None:
    info = body.get("place_results")
    return place_from_info(info) if isinstance(info, dict) else None

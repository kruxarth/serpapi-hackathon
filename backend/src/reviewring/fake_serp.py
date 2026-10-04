"""A fake SerpApi that serves a synthetic World as real-shaped JSON responses.

Used by tests, and by developers to exercise live mode end to end without
spending searches (``REVIEWRING_FAKE_SERPAPI=1``). Every value is invented.
"""

from __future__ import annotations

from typing import Any

import serpapi

from .synth import CITIES, FETCH_DAY, FETCHED, World

STATES = {
    "Pune": "Maharashtra",
    "Mumbai": "Maharashtra",
    "Nagpur": "Maharashtra",
    "Delhi NCR": "Delhi",
    "Bengaluru": "Karnataka",
    "Hyderabad": "Telangana",
    "Chennai": "Tamil Nadu",
    "Kolkata": "West Bengal",
    "Jaipur": "Rajasthan",
    "Udaipur": "Rajasthan",
    "Jodhpur": "Rajasthan",
    "Lucknow": "Uttar Pradesh",
    "Kochi": "Kerala",
    "Ahmedabad": "Gujarat",
    "Indore": "Madhya Pradesh",
    "Goa": "Goa",
}


def _address(city: str | None) -> str | None:
    if not city or city not in CITIES:
        return None
    town = "New Delhi" if city == "Delhi NCR" else city
    return f"Invented Road, {town}, {STATES[city]}"


def _relative(lo, hi) -> str:
    if lo is None or hi is None:
        return "some time ago"
    days = (FETCH_DAY - hi).days
    width = (hi - lo).days
    if width <= 1:
        return "a day ago" if days == 1 else (f"{days} days ago" if days > 1 else "3 hours ago")
    if width <= 7:
        weeks = max(1, days // 7)
        return f"{weeks} weeks ago" if weeks > 1 else "a week ago"
    if width <= 30:
        months = max(1, days // 30)
        return f"{months} months ago" if months > 1 else "a month ago"
    years = max(1, days // 365)
    return f"{years} years ago" if years > 1 else "a year ago"


class FakeSerpApi:
    """Answers ``search()`` and ``account()`` like serpapi.Client, from a World."""

    def __init__(self, world: World, *, private: set[str] | None = None) -> None:
        self.world = world
        self.private = private or set()
        self.calls: list[dict[str, Any]] = []
        self.account_data = {
            "plan_name": "Fake",
            "total_searches_left": 250,
            "plan_searches_left": 250,
            "this_month_usage": 0,
            "this_hour_searches": 0,
            "last_hour_searches": 0,
            "account_rate_limit_per_hour": 50,
            "plan_renewal_date": None,
        }

    def account(self) -> dict[str, Any]:
        return dict(self.account_data)

    def search(self, params: dict[str, Any]) -> serpapi.SerpResults:
        params = {k: v for k, v in params.items() if k != "api_key"}
        self.calls.append(params)
        engine = params["engine"]
        if engine == "google_maps_reviews":
            body = self._reviews(params)
        elif engine == "google_maps_contributor_reviews":
            body = self._history(str(params["contributor_id"]))
        else:
            body = self._place()
        body.setdefault("search_metadata", {"id": f"fake{len(self.calls):05d}", "status": "Success"})
        return serpapi.SerpResults(body, client=None)

    def _place_info(self, place) -> dict[str, Any]:
        info: dict[str, Any] = {"title": place.title, "type": place.type, "data_id": place.data_id}
        if place.lat is not None:
            info["gps_coordinates"] = {"latitude": place.lat, "longitude": place.lng}
        address = _address(place.area)
        if address:
            info["address"] = address
        return info

    def _reviews(self, params: dict[str, Any]) -> dict[str, Any]:
        w = self.world
        reviews = sorted(w.target_reviews, key=lambda r: r.posted_at or FETCHED, reverse=True)
        if params.get("sort_by") == "ratingHigh":
            reviews = sorted(reviews, key=lambda r: -(r.rating or 0))
        token = params.get("next_page_token")
        start = 0 if not token else int(token.removeprefix("tok"))
        size = 8 if not token else int(params.get("num", 20))
        page = reviews[start : start + size]
        body: dict[str, Any] = {
            "place_info": {
                "title": w.target.title,
                "address": _address(w.target.area),
                "rating": w.target.rating,
                "reviews": w.target.total_reviews,
                "type": w.target.type,
            },
            "reviews": [],
        }
        for r in page:
            user: dict[str, Any] = {"name": f"Invented Person {r.contributor_id}"}
            if r.contributor_id:
                user["contributor_id"] = r.contributor_id
            if r.reviewer_reviews is not None:
                user["reviews"] = r.reviewer_reviews
            if r.reviewer_photos is not None:
                user["photos"] = r.reviewer_photos
            body["reviews"].append(
                {
                    "review_id": r.review_id,
                    "rating": r.rating,
                    "iso_date": r.posted_at.isoformat().replace("+00:00", "Z") if r.posted_at else None,
                    "date": "recently",
                    "snippet": r.text,
                    "extracted_snippet": {"original": r.text},
                    "user": user,
                }
            )
        if start + size < len(reviews):
            body["serpapi_pagination"] = {"next_page_token": f"tok{start + size}"}
        return body

    def _history(self, cid: str) -> dict[str, Any]:
        w = self.world
        c = w.contributors.get(cid)
        if cid in self.private or c is None:
            return {"contributor": {"name": f"Invented {cid}"}, "reviews": []}
        items = []
        for h in w.histories.get(cid, []):
            place = w.places.get(h.place_key) if h.place_key else None
            item: dict[str, Any] = {
                "review_id": h.review_id,
                "rating": h.rating,
                "date": _relative(h.date_min, h.date_max),
                "snippet": h.text,
            }
            if place is not None:
                item["place_info"] = self._place_info(place)
            items.append(item)
        contributions = {k: v for k, v in c.contributions.items() if v is not None}
        profile: dict[str, Any] = {"name": f"Invented {cid}", "contributions": contributions}
        if c.level is not None:
            profile["level"] = c.level
        return {"contributor": profile, "reviews": items}

    def _place(self) -> dict[str, Any]:
        t = self.world.target
        return {"place_results": {**self._place_info(t), "rating": t.rating, "reviews": t.total_reviews}}

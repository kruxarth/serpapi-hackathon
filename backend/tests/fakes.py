"""A scripted stand-in for ``serpapi.Client`` and synthetic response bodies.

Every value here is invented. Nothing is copied from SerpApi's documentation.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
import serpapi

FAKE_KEY = "fakekey-not-real-aaaaaaaaaaaaaaaa"
DATA_ID = "0x3be7c1a2b3c4d5e6:0x1a2b3c4d5e6f7081"


def http_error(status: int, error: str | None = "boom", key: str = FAKE_KEY) -> serpapi.HTTPError:
    """Mimic the serpapi package: the wrapped requests error quotes the full URL, key included."""
    url = f"https://serpapi.com/search?engine=google_maps_reviews&api_key={key}"
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps({"error": error}).encode() if error is not None else b"not json"
    resp.url = url
    inner = requests.HTTPError(f"{status} Error for url: {url}", response=resp)
    return serpapi.HTTPError(inner)


def timeout_error(key: str = FAKE_KEY) -> serpapi.TimeoutError:
    return serpapi.TimeoutError(f"Read timed out. (url: https://serpapi.com/search?api_key={key})")


Outcome = dict[str, Any] | Exception | Callable[[dict[str, Any]], Any]


class FakeClient:
    """Answers ``search(params)`` from a script keyed by a params predicate, in call order."""

    def __init__(self, default: Outcome | None = None, account: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.queue: list[Outcome] = []
        self.default = default
        self.account_data = account
        self.api_key = FAKE_KEY

    def push(self, *outcomes: Outcome) -> FakeClient:
        self.queue.extend(outcomes)
        return self

    def search(self, params: dict[str, Any]) -> Any:
        params = dict(params)
        params["api_key"] = self.api_key  # the real client mutates params like this
        self.calls.append(params)
        outcome = self.queue.pop(0) if self.queue else self.default
        if outcome is None:
            raise AssertionError(f"unexpected search: {params}")
        if callable(outcome) and not isinstance(outcome, dict):
            outcome = outcome(params)
        if isinstance(outcome, Exception):
            raise outcome
        return serpapi.SerpResults(outcome, client=self)

    def account(self) -> dict[str, Any]:
        if self.account_data is None:
            raise AssertionError("unexpected account call")
        return dict(self.account_data, api_key=FAKE_KEY, account_email="someone@example.invalid")


def metadata(search_id: str = "fake0001") -> dict[str, Any]:
    return {"id": search_id, "status": "Success"}


def review(i: int, *, rating: int = 5, contributor: str | None = None, total: int | None = 3, when=None) -> dict:
    when = when or datetime(2026, 9, 20, 10, 0, tzinfo=UTC) - timedelta(hours=i)
    user: dict[str, Any] = {"name": f"Invented Person {i}", "link": f"https://example.invalid/u/{i}"}
    if contributor is not None:
        user["contributor_id"] = contributor
    if total is not None:
        user["reviews"] = total
    return {
        "review_id": f"rev-{i:04d}",
        "rating": rating,
        "iso_date": when.isoformat().replace("+00:00", "Z"),
        "date": "a week ago",
        "snippet": f"Invented review text number {i}",
        "extracted_snippet": {"original": f"Invented review text number {i}"},
        "user": user,
    }


def reviews_page(start: int, count: int, token: str | None, search_id: str = "fake0001") -> dict[str, Any]:
    body: dict[str, Any] = {
        "search_metadata": metadata(search_id),
        "place_info": {
            "title": "Invented Clinic",
            "address": "Somewhere, Pune, Maharashtra",
            "rating": 4.8,
            "reviews": 500,
            "type": "Dental clinic",
        },
        "reviews": [
            review(start + j, contributor=str(9000 + start + j), total=(start + j) % 7 + 1) for j in range(count)
        ],
    }
    if token:
        body["serpapi_pagination"] = {"next_page_token": token}
    return body


def history(contributor_id: str, n: int = 3, search_id: str = "fakeh001") -> dict[str, Any]:
    return {
        "search_metadata": metadata(search_id),
        "contributor": {"name": f"Invented {contributor_id}", "contributions": {"reviews": n}},
        "reviews": [
            {
                "review_id": f"h-{contributor_id}-{j}",
                "rating": 5,
                "date": f"{j + 1} weeks ago",
                "snippet": "Invented history text",
                "place_info": {
                    "title": f"Invented Place {j}",
                    "data_id": f"0x1:0x{j + 10:x}",
                    "gps_coordinates": {"latitude": 18.5 + j, "longitude": 73.8},
                },
            }
            for j in range(n)
        ],
    }

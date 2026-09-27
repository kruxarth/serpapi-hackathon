"""Gateway outcomes that stop or pause work. Messages never contain keys."""

from __future__ import annotations

from datetime import datetime


class GatewayError(Exception):
    """Base class. ``str()`` is always safe to show."""


class NoApiKey(GatewayError):
    def __init__(self) -> None:
        super().__init__("No SerpApi key is set. Add SERPAPI_API_KEY to .env, or use offline or demo mode.")


class InvalidApiKey(GatewayError):
    def __init__(self) -> None:
        super().__init__("SerpApi rejected the API key (HTTP 401). Nothing more will be requested until it is fixed.")


class BadRequest(GatewayError):
    """HTTP 400 or an error body that isn't an empty result. Not retried."""


class BudgetRefused(GatewayError):
    """The monthly budget or a configured cap doesn't cover the request."""

    def __init__(self, message: str, needed: int, remaining: int) -> None:
        super().__init__(message)
        self.needed = needed
        self.remaining = remaining


class Paused(GatewayError):
    """Work must wait: hourly limit, 429, or repeated upstream failures."""

    def __init__(self, reason: str, resume_at: datetime | None, message: str) -> None:
        super().__init__(message)
        self.reason = reason  # hourly_limit | rate_limited | upstream_error
        self.resume_at = resume_at


class NotCached(GatewayError):
    """Offline mode or a dry run needed a request that isn't in the cache."""

    def __init__(self, label: str, request_key: str) -> None:
        super().__init__(f"Not in cache: {label} (would cost 1 search)")
        self.label = label
        self.request_key = request_key

"""Relative dates ("3 weeks ago") to absolute IST date ranges (spec 9.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")

_WORDS = {"a": 1, "an": 1, "one": 1}
_REL = re.compile(
    r"^(?:(?P<now>just now|moments? ago)|(?P<n>\d+|an?|one)\s+(?P<unit>minute|hour|day|week|month|year)s?\s+ago)$"
)
_EDITED = re.compile(r"^edited\s*(?:[:\-·]\s*)?", re.IGNORECASE)


@dataclass(frozen=True)
class RelativeRange:
    min_days: int  # days before the fetch, inclusive
    max_days: int
    edited: bool


@dataclass(frozen=True)
class DateRange:
    date_min: date | None
    date_max: date | None
    edited: bool

    @property
    def known(self) -> bool:
        return self.date_min is not None and self.date_max is not None

    @property
    def precision_days(self) -> int | None:
        if not self.known:
            return None
        return (self.date_max - self.date_min).days  # type: ignore[operator]

    def overlaps(self, other: DateRange) -> bool:
        if not (self.known and other.known):
            return False
        return self.date_min <= other.date_max and other.date_min <= self.date_max  # type: ignore[operator]


def parse_relative(text: str | None) -> RelativeRange | None:
    """Map a relative date string to a range of days before the fetch, per the spec's table."""
    if not text:
        return None
    s = " ".join(text.strip().lower().split())
    edited = bool(_EDITED.match(s))
    s = _EDITED.sub("", s).strip()
    m = _REL.match(s)
    if not m:
        return None
    if m.group("now"):
        return RelativeRange(0, 1, edited)
    raw = m.group("n")
    n = _WORDS.get(raw, None) if not raw.isdigit() else int(raw)
    if n is None:
        return None
    unit = m.group("unit")
    single = not raw.isdigit()  # "a week ago" has its own row in the table
    if unit in ("minute", "hour"):
        return RelativeRange(0, 1, edited)
    if unit == "day":
        return RelativeRange(1, 2, edited) if single else RelativeRange(n, n + 1, edited)
    if unit == "week":
        return RelativeRange(7, 14, edited) if single else RelativeRange(7 * n, 7 * n + 7, edited)
    if unit == "month":
        return RelativeRange(30, 60, edited) if single else RelativeRange(30 * n, 30 * n + 30, edited)
    return RelativeRange(365, 730, edited) if single else RelativeRange(365 * n, 365 * n + 365, edited)


def ist_date(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(IST).date()


def absolute_range(text: str | None, fetched_at: datetime, photo_dates: list[str] | None = None) -> DateRange:
    """Absolute IST calendar dates for a relative string, from that response's own fetch time.

    A photo date inside the range raises the earliest date: a review can't predate its photos.
    """
    rel = parse_relative(text)
    edited = bool(text and _EDITED.match(text.strip()))
    if rel is None:
        return DateRange(None, None, edited)
    fetched = ist_date(fetched_at)
    lo = fetched - timedelta(days=rel.max_days)
    hi = fetched - timedelta(days=rel.min_days)
    inside = []
    for raw in photo_dates or []:
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if lo <= d <= hi:
            inside.append(d)
    if inside:
        lo = max(inside)
    return DateRange(lo, hi, rel.edited)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

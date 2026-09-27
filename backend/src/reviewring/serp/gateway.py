"""The one and only path to SerpApi (Rules 1-3, spec 5.3).

Every request goes through :class:`Gateway`, which
- serves the versioned cache first (a forced refresh adds a new version),
- enforces the monthly, rolling-hour and per-analysis caps from the ledger and
  the Account API, whichever is stricter,
- stores each raw response before anything parses it,
- records every request that reached SerpApi in the ledger,
- handles 401 / 429 / 400 / 5xx / timeouts as the spec requires, and
- never lets a key into logs or error messages.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import serpapi

from .. import config, db, redact
from . import catalog
from .catalog import SerpRequest
from .errors import BadRequest, BudgetRefused, GatewayError, InvalidApiKey, NoApiKey, NotCached, Paused

log = logging.getLogger(__name__)

HOUR = timedelta(minutes=60)
BILLED = ("ok", "empty")
_EMPTY_RESULT = re.compile(r"hasn'?t returned any results|no results", re.IGNORECASE)
_ACCOUNT_STRIP = ("api_key", "account_email")


@dataclass
class Response:
    request: SerpRequest
    body: dict[str, Any]
    status: str  # ok | empty
    version: int
    fetched_at: datetime
    search_id: str | None
    from_cache: bool


@dataclass
class PageResult:
    """Target review pages, fetched as one atomic step."""

    responses: list[Response]
    complete: bool  # every needed page was obtained, or the reviews ran out
    missing_pages: int = 0  # pages that would still cost searches
    note: str = ""


@dataclass
class BudgetStatus:
    monthly_cap: int
    hourly_cap: int
    per_analysis_cap: int
    ledger_month: int
    ledger_hour: int
    month_remaining: int
    hour_remaining: int
    analysis_used: int | None = None
    analysis_remaining: int | None = None
    account: dict[str, Any] | None = None
    account_fetched_at: str | None = None
    hour_resume_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class PlannedRequest:
    label: str
    engine: str
    request_key: str | None  # None when it depends on a response not fetched yet
    cost: int = 1


@dataclass
class _AccountSnapshot:
    fetched_at: datetime
    data: dict[str, Any] = field(default_factory=dict)


def strip_account(data: dict[str, Any]) -> dict[str, Any]:
    """Remove the key and the email the Account API echoes back (Rule 4)."""
    return {k: v for k, v in data.items() if k not in _ACCOUNT_STRIP and "email" not in k.lower()}


def next_page_token(body: dict[str, Any]) -> str | None:
    pagination = body.get("serpapi_pagination") or {}
    token = pagination.get("next_page_token")
    return token or None


def pages_needed(n_reviews: int) -> int:
    return 1 + math.ceil(max(0, n_reviews - catalog.FIRST_PAGE_SIZE) / catalog.PAGE_SIZE)


class Gateway:
    """Modes: ``live`` (cache, then SerpApi within budget) or ``offline`` (cache only).

    With ``dry_run=True`` nothing is requested: cache misses are recorded in
    :attr:`planned` and raise :class:`NotCached`.
    """

    def __init__(
        self,
        *,
        mode: str = "live",
        dry_run: bool = False,
        db_path: Path | str | None = None,
        secrets: config.Secrets | None = None,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = db.utcnow,
    ) -> None:
        if mode not in ("live", "offline"):
            raise ValueError(f"unknown gateway mode {mode!r}")
        redact.install()
        self.mode = mode
        self.dry_run = dry_run
        self.db_path = db_path
        self.secrets = secrets or config.load_secrets()
        for value in self.secrets.values():
            redact.register_secret(value)
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.RLock()
        self._local = threading.local()
        self._inflight = 0
        self._halted = False
        self._account: _AccountSnapshot | None = None
        self.planned: list[PlannedRequest] = []

    # ------------------------------------------------------------------ plumbing

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = db.connect(self.db_path)
            self._local.conn = conn
        return conn

    def _client_or_raise(self) -> Any:
        if not self.secrets.serpapi_key:
            raise NoApiKey()
        if self._client is None:
            self._client = serpapi.Client(
                api_key=self.secrets.serpapi_key,
                timeout=config.tunable("budget", "request_timeout_seconds"),
            )
        return self._client

    @property
    def live(self) -> bool:
        return self.mode == "live" and not self.dry_run

    # ------------------------------------------------------------------ cache

    def lookup_cache(self, req: SerpRequest) -> Response | None:
        row = (
            self._conn()
            .execute(
                "SELECT version, body, fetched_at, search_id, status FROM raw_responses "
                "WHERE request_key = ? AND status IN ('ok', 'empty') ORDER BY version DESC LIMIT 1",
                (req.key,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return Response(
            request=req,
            body=json.loads(row["body"]),
            status=row["status"],
            version=row["version"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            search_id=row["search_id"],
            from_cache=True,
        )

    def _store_raw(self, req: SerpRequest, body_text: str, status: str, search_id: str | None) -> tuple[int, datetime]:
        """Persist a raw response before anything parses it (Rule 3)."""
        now = self._clock()
        conn = self._conn()
        with self._lock:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM raw_responses WHERE request_key = ?", (req.key,)
            ).fetchone()
            version = row[0] + 1
            conn.execute(
                "INSERT INTO raw_responses (request_key, version, engine, params, body, fetched_at, search_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    req.key,
                    version,
                    req.engine,
                    req.canonical(),
                    redact.scrub_secrets(body_text),
                    db.iso(now),
                    search_id,
                    status,
                ),
            )
        return version, now

    def _record_ledger(self, req: SerpRequest, search_id: str | None, analysis_id: str | None, status: str) -> None:
        self._conn().execute(
            "INSERT INTO ledger (timestamp, engine, request_key, search_id, analysis_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (db.iso(self._clock()), req.engine, req.key, search_id, analysis_id, status),
        )

    # ------------------------------------------------------------------ budget

    def refresh_account(self) -> dict[str, Any] | None:
        """Call the free Account API. Returns the stripped data, or None when offline."""
        if self.mode != "live":
            return None
        client = self._client_or_raise()
        try:
            data = client.account()
        except serpapi.HTTPError as exc:
            if getattr(exc, "status_code", None) == 401:
                self._halted = True
                raise InvalidApiKey() from None
            raise GatewayError(f"Account API failed: {redact.safe_error(exc)}") from None
        except (serpapi.TimeoutError, OSError) as exc:
            raise GatewayError(f"Account API failed: {redact.safe_error(exc)}") from None
        stripped = strip_account(dict(data))
        with self._lock:
            self._account = _AccountSnapshot(fetched_at=self._clock(), data=stripped)
        return stripped

    def _billed_since(self, since: datetime, analysis_id: str | None = None) -> list[datetime]:
        sql = "SELECT timestamp FROM ledger WHERE status IN ('ok', 'empty') AND timestamp >= ?"
        args: list[Any] = [db.iso(since)]
        if analysis_id is not None:
            sql += " AND analysis_id = ?"
            args.append(analysis_id)
        rows = self._conn().execute(sql + " ORDER BY timestamp", args).fetchall()
        return [datetime.fromisoformat(r[0]) for r in rows]

    def _analysis_used(self, analysis_id: str) -> int:
        row = (
            self._conn()
            .execute("SELECT COUNT(*) FROM ledger WHERE status IN ('ok', 'empty') AND analysis_id = ?", (analysis_id,))
            .fetchone()
        )
        return int(row[0])

    def budget_status(self, analysis_id: str | None = None, need: int = 1) -> BudgetStatus:
        now = self._clock()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_cap = int(config.tunable("budget", "monthly_cap"))
        hourly_cap = int(config.tunable("budget", "hourly_cap"))
        per_analysis = int(config.tunable("budget", "per_analysis_cap"))

        month_rows = self._billed_since(month_start)
        hour_rows = self._billed_since(now - HOUR)
        month_remaining = monthly_cap - len(month_rows)
        hour_remaining = hourly_cap - len(hour_rows)

        account = self._account
        account_hour_binding = False
        if account is not None:
            since = len(self._billed_since(account.fetched_at))
            left = account.data.get("total_searches_left")
            if isinstance(left, int):
                month_remaining = min(month_remaining, left - since)
            rate = account.data.get("account_rate_limit_per_hour")
            this_hour = account.data.get("this_hour_searches")
            if isinstance(rate, int) and isinstance(this_hour, int):
                account_left = rate - this_hour - since
                if account_left < hour_remaining:
                    hour_remaining = account_left
                    account_hour_binding = True

        with self._lock:
            month_remaining -= self._inflight
            hour_remaining -= self._inflight

        resume_at: datetime | None = None
        if hour_remaining < need:
            if account_hour_binding:
                resume_at = now.replace(minute=0, second=0, microsecond=0) + HOUR
            else:
                # Drop the oldest entries in the window until `need` slots are free.
                drop = len(hour_rows) - (hourly_cap - need)
                if 0 < drop <= len(hour_rows):
                    resume_at = hour_rows[drop - 1] + HOUR
                else:
                    resume_at = now + HOUR

        status = BudgetStatus(
            monthly_cap=monthly_cap,
            hourly_cap=hourly_cap,
            per_analysis_cap=per_analysis,
            ledger_month=len(month_rows),
            ledger_hour=len(hour_rows),
            month_remaining=max(0, month_remaining),
            hour_remaining=max(0, hour_remaining),
            account=dict(account.data) if account else None,
            account_fetched_at=db.iso(account.fetched_at) if account else None,
            hour_resume_at=db.iso(resume_at) if resume_at else None,
        )
        if analysis_id is not None:
            used = self._analysis_used(analysis_id)
            status.analysis_used = used
            status.analysis_remaining = max(0, per_analysis - used)
        return status

    def _acquire(self, n: int, analysis_id: str | None) -> None:
        """Check the caps for n more searches and hold them as in-flight."""
        with self._lock:
            status = self.budget_status(analysis_id, need=n)
            if status.month_remaining < n:
                raise BudgetRefused(
                    f"Monthly budget too low: {n} searches needed, {status.month_remaining} left.",
                    needed=n,
                    remaining=status.month_remaining,
                )
            if status.analysis_remaining is not None and status.analysis_remaining < n:
                raise BudgetRefused(
                    f"Per-analysis cap reached: {n} searches needed, {status.analysis_remaining} left of "
                    f"{status.per_analysis_cap}.",
                    needed=n,
                    remaining=status.analysis_remaining,
                )
            if status.hour_remaining < n:
                resume = datetime.fromisoformat(status.hour_resume_at) if status.hour_resume_at else None
                raise Paused("hourly_limit", resume, "Waiting for the hourly search limit.")
            self._inflight += n

    def _release(self, n: int) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - n)

    @contextmanager
    def reserve(self, n: int, analysis_id: str | None = None) -> Iterator[None]:
        """Hold n searches for an atomic step. Unused slots are released afterwards."""
        self._acquire(n, analysis_id)
        self._local.reserved = getattr(self._local, "reserved", 0) + n
        try:
            yield
        finally:
            left = self._local.reserved
            self._local.reserved = 0
            self._release(left)

    # ------------------------------------------------------------------ fetching

    def fetch(self, req: SerpRequest, *, analysis_id: str | None = None, force_refresh: bool = False) -> Response:
        if not force_refresh:
            cached = self.lookup_cache(req)
            if cached is not None:
                return cached
        if not self.live:
            self.planned.append(PlannedRequest(req.label, req.engine, req.key))
            raise NotCached(req.label, req.key)
        if self._halted:
            raise InvalidApiKey()
        client = self._client_or_raise()

        reserved = getattr(self._local, "reserved", 0) > 0
        if reserved:
            self._local.reserved -= 1  # this slot is now consumed by the call below
        else:
            self._acquire(1, analysis_id)
        try:
            return self._call_with_retry(client, req, analysis_id)
        finally:
            self._release(1)

    def _call_with_retry(self, client: Any, req: SerpRequest, analysis_id: str | None) -> Response:
        for attempt in (1, 2):
            try:
                return self._call(client, req, analysis_id)
            except _Retryable as exc:
                log.warning("SerpApi %s failed (%s), attempt %d", req.label, exc.description, attempt)
                if attempt == 1:
                    self._sleep(float(config.tunable("budget", "retry_delay_seconds")))
                    continue
                raise Paused(
                    "upstream_error",
                    self._clock() + timedelta(seconds=float(config.tunable("budget", "retry_delay_seconds"))),
                    f"SerpApi is failing ({exc.description}); paused. Resume to try again.",
                ) from None
        raise AssertionError("unreachable")

    def _call(self, client: Any, req: SerpRequest, analysis_id: str | None) -> Response:
        try:
            # A fresh dict: the serpapi client writes the key into the params it's given.
            result = client.search(dict(req.all_params()))
        except serpapi.HTTPError as exc:
            code = getattr(exc, "status_code", -1)
            if code == -1:
                raise _Retryable(redact.safe_error(exc)) from None
            body_error = redact.redact(getattr(exc, "error", None) or "")
            self._store_raw(req, json.dumps({"error": body_error, "http_status": code}), "error", None)
            self._record_ledger(req, None, analysis_id, "error")
            if code == 401:
                self._halted = True
                raise InvalidApiKey() from None
            if code == 429:
                status = self.budget_status()
                resume = datetime.fromisoformat(status.hour_resume_at) if status.hour_resume_at else None
                raise Paused(
                    "rate_limited", resume or self._clock() + HOUR, "SerpApi rate limit reached (HTTP 429)."
                ) from None
            if code >= 500:
                raise _Retryable(f"HTTP {code}") from None
            raise BadRequest(f"SerpApi rejected the request (HTTP {code}): {body_error or 'no details'}") from None
        except serpapi.TimeoutError as exc:
            raise _Retryable(redact.safe_error(exc)) from None
        except OSError as exc:
            raise _Retryable(redact.safe_error(exc)) from None

        if isinstance(result, dict) or hasattr(result, "data"):
            body = dict(getattr(result, "data", result))
            body_text = json.dumps(body, ensure_ascii=False)
        else:
            body = None
            body_text = json.dumps({"error": "non-JSON response", "text": str(result)[:2000]})

        search_id = None
        status = "error"
        if body is not None:
            search_id = (body.get("search_metadata") or {}).get("id")
            error = body.get("error")
            if not error:
                status = "ok"
            elif _EMPTY_RESULT.search(str(error)):
                status = "empty"
        version, fetched_at = self._store_raw(req, body_text, status, search_id)
        self._record_ledger(req, search_id, analysis_id, status)

        if status == "error":
            detail = redact.redact((body or {}).get("error") or "unexpected response")
            raise BadRequest(f"SerpApi returned an error for {req.label}: {detail}")
        stored = self.lookup_cache(req)
        assert stored is not None and stored.version == version
        return Response(req, stored.body, status, version, fetched_at, search_id, from_cache=False)

    def fetch_pages(
        self,
        data_id: str,
        n_reviews: int,
        *,
        analysis_id: str | None = None,
        force_refresh: bool = False,
    ) -> PageResult:
        """Fetch the newest ``n_reviews`` target reviews as one atomic step (spec 5.3).

        Page tokens chain, so the budget for every missing page is checked and
        held before the first request, and nothing pauses between pages.
        """
        needed = pages_needed(n_reviews)
        responses: list[Response] = []
        req = catalog.reviews_page(data_id)
        while len(responses) < needed:
            cached = None if force_refresh else self.lookup_cache(req)
            if cached is None:
                break
            responses.append(cached)
            token = next_page_token(cached.body)
            if not token:
                return PageResult(responses, complete=True)
            req = catalog.reviews_page(data_id, token)
        missing = needed - len(responses)
        if missing == 0:
            return PageResult(responses, complete=True)

        if not self.live:
            self.planned.append(PlannedRequest(req.label, req.engine, req.key))
            for _ in range(missing - 1):
                self.planned.append(PlannedRequest("reviews page (depends on previous page)", req.engine, None))
            return PageResult(
                responses, complete=False, missing_pages=missing, note=f"{missing} review pages not cached"
            )

        with self.reserve(missing, analysis_id):
            while len(responses) < needed:
                try:
                    resp = self.fetch(req, analysis_id=analysis_id, force_refresh=force_refresh)
                except (Paused, BadRequest) as exc:
                    got = len(responses)
                    return PageResult(
                        responses,
                        complete=False,
                        missing_pages=needed - got,
                        note=f"Review pagination stopped after {got} pages: {exc}",
                    )
                responses.append(resp)
                token = next_page_token(resp.body)
                if not token:
                    break
                req = catalog.reviews_page(data_id, token)
        return PageResult(responses, complete=True)


class _Retryable(Exception):
    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description

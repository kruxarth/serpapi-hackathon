"""Collection: from user input to a complete AnalysisInput, within the search budget.

Steps (spec 5.1, 9.3): resolve the place, fetch the newest N reviews (one atomic
step), score reviewers, expand round 1 (K1 priority + B baseline), stop early if
no round-1 pair meets the edge rule, otherwise expand round 2 (K2 more).

Everything fetched is cached, so resuming a paused or failed run simply runs it
again: cached requests cost nothing and nothing is requested twice.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import ALGORITHM_VERSION, config, db
from .engine.features import compute_text_features
from .engine.graph import build_pairs, edges
from .engine.priority import Selection, score_reviews, select_round1, select_round2, select_voice
from .engine.target_signals import detect_bursts
from .engine.textstyle import keyword_style
from .model import AnalysisInput, Contributor, Expansion, HistoryReview, Place
from .normalize.geo import AreaPoint, assign_areas
from .parse import contributor_history, lookup_place, target_place, target_reviews
from .resolve import InputRefused, ResolvedInput, lookup, parse_input, target_coords_request
from .serp import catalog
from .serp.errors import BudgetRefused, GatewayError, InvalidApiKey, NotCached, Paused
from .serp.gateway import Gateway, Response, next_page_token, pages_needed

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


@dataclass
class Event:
    type: str  # resolving | fetching_reviews | scoring | expanding | early_stop | building_graph | ...
    message: str
    searches_used: int
    data: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: db.iso(db.utcnow()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "searches_used": self.searches_used,
            "data": self.data,
            "at": self.at,
        }


@dataclass
class CollectParams:
    n: int = 0
    k1: int = 0
    baseline: int = 0
    k2: int = 0
    voice_picks: int = 0
    stop_after_round1: bool = False
    force_refresh: bool = False
    pick: str | None = None  # data_id chosen from name-search candidates

    @classmethod
    def from_config(cls, **overrides: Any) -> CollectParams:
        c = config.load_tunables()["collection"]
        p = cls(n=c["n_reviews"], k1=c["k1"], baseline=c["baseline"], k2=c["k2"], voice_picks=c.get("voice_picks", 0))
        for k, v in overrides.items():
            if v is not None:
                setattr(p, k, v)
        return p

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Outcome:
    status: str  # done | paused | needs_input | cancelled | error
    input: AnalysisInput | None = None
    message: str = ""
    resume_at: datetime | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    early_stop: bool = False
    selection: dict[str, Any] = field(default_factory=dict)


def new_analysis_id() -> str:
    return uuid.uuid4().hex[:12]


class Collector:
    def __init__(
        self,
        gateway: Gateway,
        input_text: str,
        params: CollectParams | None = None,
        *,
        analysis_id: str | None = None,
        on_event: Callable[[Event], None] | None = None,
        cancel: threading.Event | None = None,
        resolved: ResolvedInput | None = None,
    ) -> None:
        self.gw = gateway
        self.input_text = input_text
        self.params = params or CollectParams.from_config()
        self.analysis_id = analysis_id or new_analysis_id()
        self.on_event = on_event or (lambda e: None)
        self.cancel_event = cancel or threading.Event()
        self.resolved = resolved
        self.conn = db.connect(gateway.db_path)
        self.state: dict[str, Any] = {}
        self._load_or_create()

    # ------------------------------------------------------------------ bookkeeping

    def _load_or_create(self) -> None:
        row = self.conn.execute("SELECT state, params FROM analyses WHERE id = ?", (self.analysis_id,)).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO analyses (id, input, params, mode, status, stage, started_at, algorithm_version, state) "
                "VALUES (?, ?, ?, ?, 'queued', 'queued', ?, ?, '{}')",
                (
                    self.analysis_id,
                    self.input_text,
                    json.dumps(self.params.as_dict()),
                    self.gw.mode,
                    db.iso(db.utcnow()),
                    ALGORITHM_VERSION,
                ),
            )
        else:
            self.state = json.loads(row["state"] or "{}")
            if row["params"]:
                saved = json.loads(row["params"])
                pick = self.params.pick
                self.params = CollectParams(**saved)
                self.params.pick = pick or self.params.pick

    def _update(self, **fields: Any) -> None:
        fields["searches_used"] = self.searches_used()
        fields["state"] = json.dumps(self.state, default=str)
        fields["params"] = json.dumps(self.params.as_dict())
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE analyses SET {cols} WHERE id = ?", (*fields.values(), self.analysis_id))

    def searches_used(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM ledger WHERE analysis_id = ? AND status IN ('ok', 'empty')", (self.analysis_id,)
        ).fetchone()
        return int(row[0])

    def emit(self, type_: str, message: str, **data: Any) -> None:
        self._update(stage=type_)
        self.on_event(Event(type_, message, self.searches_used(), data))

    def show(self, type_: str, message: str, **data: Any) -> None:
        """An event for the live view only (no stage change): counts, stars and day offsets, never ids or names."""
        self.on_event(Event(type_, message, self.searches_used(), data))

    def _show_reviews(self, inp: AnalysisInput) -> None:
        newest = max((r.posted_at for r in inp.target_reviews if r.posted_at), default=None)
        self._index = {}
        for i, r in enumerate(inp.target_reviews):
            if r.contributor_id and r.contributor_id not in self._index:
                self._index[r.contributor_id] = i
        rows = [
            [r.rating, (newest - r.posted_at).days if newest and r.posted_at else None, r.reviewer_reviews]
            for r in inp.target_reviews
        ]
        self.show(
            "reviews_loaded",
            f"Read {len(rows)} reviews",
            rating=inp.target.rating,
            total=inp.target.total_reviews,
            reviews=rows,
        )

    def _show_history(self, cid: str) -> None:
        """One reviewer's history, as stars and ages in days, for the live view."""
        index = getattr(self, "_index", {}).get(cid)
        cached = self.gw.lookup_cache(catalog.contributor_history(cid))
        if index is None or cached is None:
            return
        contributor, history, places = contributor_history(cached.body, cid, cached.fetched_at, cached.status)
        today = cached.fetched_at.date()
        points = []
        for h in history:
            if h.date_min is None or h.date_max is None:
                continue
            mid = h.date_min + (h.date_max - h.date_min) / 2
            points.append([(today - mid).days, h.rating])
        areas = {p.area for p in places if p.area}
        self.show(
            "history",
            f"Opened a reviewer with {contributor.total_reviews or len(history)} reviews",
            index=index,
            status=contributor.status,
            total=contributor.total_reviews,
            visible=len(history),
            areas=len(areas),
            points=points,
        )

    def _show_picks(self, picks: list[tuple[str, str, int]]) -> None:
        index = getattr(self, "_index", {})
        rows = [[index[c], reason, round_] for c, reason, round_ in picks if c in index]
        self.show("picks", f"Picked {len(rows)} reviewers to open", picks=rows)

    def _show_links(self, pairs) -> None:
        index = getattr(self, "_index", {})
        links = sorted({tuple(sorted((index[u], index[v]))) for u, v in pairs if u in index and v in index})
        self.show("links", f"{len(links)} linked pair{'' if len(links) == 1 else 's'} of reviewers", pairs=links)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    # ------------------------------------------------------------------ steps

    def _resolve(self) -> str | None:
        if self.state.get("data_id"):
            return self.state["data_id"]
        self.emit("resolving", "Identifying the place")
        resolved = self.resolved or parse_input(self.input_text)
        self.state.update({"input_kind": resolved.kind, "lat": resolved.lat, "lng": resolved.lng})
        if resolved.data_id:
            self.state["data_id"] = resolved.data_id
            return resolved.data_id
        candidates = lookup(self.gw, resolved, self.analysis_id)
        if self.params.pick:
            chosen = [c for c in candidates if c.data_id == self.params.pick.lower()]
        else:
            chosen = candidates if len(candidates) == 1 else []
        if len(chosen) != 1 or not chosen[0].data_id:
            self.state["candidates"] = [c.__dict__ for c in candidates]
            return None
        c = chosen[0]
        self.state.update({"data_id": c.data_id, "lat": c.lat, "lng": c.lng})
        return c.data_id

    def _pages(self, data_id: str) -> list[Response]:
        self.emit("fetching_reviews", f"Fetching the newest {self.params.n} reviews")
        result = self.gw.fetch_pages(
            data_id, self.params.n, analysis_id=self.analysis_id, force_refresh=self.params.force_refresh
        )
        if result.missing_pages and not self.gw.live:
            self._missing(f"{result.missing_pages} review page(s)", result.missing_pages)
        elif result.note:
            self._note(result.note)
        if not result.responses and result.missing_pages:
            raise GatewayError(
                f"The reviews for this place aren't cached; fetching them would cost {result.missing_pages} "
                "searches. Switch to live mode to fetch them."
            )
        return result.responses

    def _note(self, note: str) -> None:
        notes = self.state.setdefault("notes", [])
        if note not in notes:
            notes.append(note)

    def _missing(self, what: str, cost: int) -> None:
        """Offline mode: remember what wasn't cached and what it would cost."""
        missing = self.state.setdefault("missing", {})
        missing[what] = cost

    def _expand(self, contributors: list[str], round_: int) -> None:
        """Fetch histories with bounded concurrency. Pauses only between histories."""
        todo = [c for c in contributors if self.gw.lookup_cache(catalog.contributor_history(c)) is None]
        total = len(contributors)
        done = total - len(todo)
        self.emit(
            "expanding", f"Round {round_}: {done} of {total} reviewer histories", round=round_, done=done, total=total
        )
        for cid in contributors:
            if cid not in todo:
                self._show_history(cid)
        if not todo:
            return
        stop = threading.Event()
        errors: list[BaseException] = []
        lock = threading.Lock()

        def work(cid: str) -> None:
            nonlocal done
            if stop.is_set() or self.cancel_event.is_set():
                return
            try:
                self.gw.fetch(catalog.contributor_history(cid), analysis_id=self.analysis_id)
            except NotCached:
                with lock:
                    self.state.setdefault("missing_histories", [])
                    if cid not in self.state["missing_histories"]:
                        self.state["missing_histories"].append(cid)
                return
            except (Paused, BudgetRefused, InvalidApiKey) as exc:
                stop.set()
                with lock:
                    errors.append(exc)
                return
            except GatewayError as exc:  # a 400 for one reviewer: record it, keep going
                with lock:
                    self.state.setdefault("history_errors", {})[cid] = str(exc)
                return
            with lock:
                done += 1
                self.emit(
                    "expanding",
                    f"Round {round_}: {done} of {total} reviewer histories",
                    round=round_,
                    done=done,
                    total=total,
                )
                self._show_history(cid)

        workers = int(config.tunable("collection", "history_concurrency"))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))
        self._check_cancel()
        if errors:
            raise errors[0]
        if self.state.get("missing_histories"):
            n = len(self.state["missing_histories"])
            self._missing("reviewer histories", n)

    # ------------------------------------------------------------------ run

    def run(self) -> Outcome:
        self._update(status="running", error=None)
        try:
            outcome = self._run()
        except Cancelled:
            self._update(status="cancelled", finished_at=db.iso(db.utcnow()))
            self.on_event(
                Event("cancelled", "Cancelled. Everything fetched so far stays cached.", self.searches_used())
            )
            return Outcome("cancelled", message="Cancelled")
        except Paused as exc:
            self.state["paused"] = {"reason": exc.reason, "resume_at": db.iso(exc.resume_at) if exc.resume_at else None}
            self._update(status="paused")
            self.on_event(Event("paused", str(exc), self.searches_used(), dict(self.state["paused"])))
            return Outcome("paused", message=str(exc), resume_at=exc.resume_at)
        except (GatewayError, InputRefused) as exc:
            self._update(status="error", error=str(exc), finished_at=db.iso(db.utcnow()))
            self.on_event(Event("error", str(exc), self.searches_used()))
            return Outcome("error", message=str(exc))
        self.state.pop("paused", None)
        if outcome.status == "needs_input":
            self._update(status="needs_input")
        else:
            self._update(status="collected")
        return outcome

    def _run(self) -> Outcome:
        data_id = self._resolve()
        self._check_cancel()
        if data_id is None:
            self.on_event(
                Event(
                    "needs_input",
                    "Several places match. Pick one.",
                    self.searches_used(),
                    {"candidates": self.state.get("candidates", [])},
                )
            )
            return Outcome(
                "needs_input", message="Several places match. Pick one.", candidates=self.state.get("candidates", [])
            )
        self._update(place_key=data_id)

        pages = self._pages(data_id)
        self._check_cancel()
        if not pages:
            raise GatewayError("No reviews could be fetched for this place.")

        inp = build_input(self.gw, data_id, pages, self.params.n, [], self.state)
        if needs_top_rated(inp):
            self._top_rated(data_id)
            self._check_cancel()
        self._show_reviews(inp)
        self.emit("scoring", "Scoring reviewers")
        features = compute_text_features(inp)
        bursts = detect_bursts(inp.target_reviews)
        keyword_ids = set(keyword_style(inp.target_reviews, inp.target)["review_ids"])
        candidates = score_reviews(inp.target_reviews, bursts, features, keyword_ids)
        selection = select_round1(candidates, data_id, self.params.k1, self.params.baseline)
        add_voice_picks(selection, inp.target_reviews, self.params.voice_picks, keyword_ids)
        round1 = selection.round1 + selection.baseline + selection.voice
        self.state["selection"] = {
            "round1": selection.round1,
            "baseline": selection.baseline,
            "voice": selection.voice,
            "candidates": len(candidates),
        }
        self._show_picks(
            [(c, "priority", 1) for c in selection.round1]
            + [(c, "baseline", 1) for c in selection.baseline]
            + [(c, "voice", 1) for c in selection.voice]
        )

        self._expand(round1, 1)
        expansions = [Expansion(c, 1, "priority") for c in selection.round1]
        expansions += [Expansion(c, 1, "baseline") for c in selection.baseline]
        expansions += [Expansion(c, 1, "voice") for c in selection.voice]
        inp = build_input(self.gw, data_id, pages, self.params.n, expansions, self.state)
        self._ensure_target_coords(inp, data_id)
        inp = build_input(self.gw, data_id, pages, self.params.n, expansions, self.state)

        self.emit("building_graph", "Checking round-1 reviewers for shared places")
        found = edges(build_pairs(inp, round1))
        self._show_links(found)
        early = not found or self.params.stop_after_round1 or not selection.remaining
        if early:
            saved = min(self.params.k2, len(selection.remaining))
            reason = "stop_after_round1" if found and self.params.stop_after_round1 else "no_overlap"
            self.state["early_stop"] = {"reason": reason, "searches_saved": saved if not found else saved}
            if not found:
                self.emit("early_stop", "No ring-like pattern among the highest-priority reviewers", saved=saved)
        else:
            round2 = select_round2(selection, inp.target_reviews, features, self.params.k2)
            self.state["selection"]["round2"] = round2
            self._show_picks([(c, "priority", 2) for c in round2])
            self._expand(round2, 2)
            expansions += [Expansion(c, 2, "priority") for c in round2]
            inp = build_input(self.gw, data_id, pages, self.params.n, expansions, self.state)
            self._show_links(edges(build_pairs(inp, [e.contributor_id for e in expansions])))
        self._check_cancel()
        inp.params = self.params.as_dict()
        return Outcome("done", input=inp, early_stop=early, selection=dict(self.state["selection"]))

    def _top_rated(self, data_id: str) -> None:
        """Sample the highest-rated reviews (spec extension; 3 searches): where a high rating comes from."""
        pages = int(config.tunable("rating_gap", "top_rated_pages"))
        self.emit("top_rated", "The displayed rating is far above the newest reviews; sampling the highest-rated ones")
        token = None
        for _ in range(pages):
            req = catalog.top_rated_page(data_id, token)
            try:
                resp = self.gw.fetch(req, analysis_id=self.analysis_id)
            except NotCached:
                self._missing("highest-rated review pages", pages)
                return
            token = next_page_token(resp.body)
            if not token:
                return

    def _ensure_target_coords(self, inp: AnalysisInput, data_id: str) -> None:
        """Free if any history contains the target; otherwise 1 lookup by data_cid (spec 8)."""
        if inp.target.lat is not None and inp.target.lng is not None:
            self.state.setdefault("coords_source", "history" if self.state.get("lat") is None else "url")
            return
        try:
            resp = self.gw.fetch(target_coords_request(data_id), analysis_id=self.analysis_id)
        except NotCached:
            self._missing("target coordinates", 1)
            self.state["coords_source"] = "unknown"
            return
        place = lookup_place(resp.body)
        if place and place.lat is not None:
            self.state.update({"lat": place.lat, "lng": place.lng, "coords_source": "lookup"})
        else:
            self.state["coords_source"] = "unknown"


# ---------------------------------------------------------------------- input assembly


def build_input(
    gw: Gateway,
    data_id: str,
    pages: list[Response],
    n: int,
    expansions: list[Expansion],
    state: dict[str, Any],
) -> AnalysisInput:
    """Assemble an AnalysisInput from cached responses only (no requests)."""
    target = target_place(pages[0].body, data_id)
    if state.get("lat") is not None and state.get("lng") is not None:
        target.lat, target.lng = float(state["lat"]), float(state["lng"])
    reviews = []
    seen: set[str] = set()
    for page in pages:
        for r in target_reviews(page.body):
            if r.review_id not in seen:
                seen.add(r.review_id)
                reviews.append(r)
    reviews = reviews[:n]

    places: dict[str, Place] = {}
    contributors: dict[str, Contributor] = {}
    histories: dict[str, list[HistoryReview]] = {}
    for exp in expansions:
        cached = gw.lookup_cache(catalog.contributor_history(exp.contributor_id))
        if cached is None:
            errors = state.get("history_errors", {})
            status = "error" if exp.contributor_id in errors else "missing"
            contributors[exp.contributor_id] = Contributor(exp.contributor_id, status=status)
            histories[exp.contributor_id] = []
            continue
        contributor, history, hist_places = contributor_history(
            cached.body, exp.contributor_id, cached.fetched_at, cached.status
        )
        contributors[exp.contributor_id] = contributor
        histories[exp.contributor_id] = history
        for p in hist_places:
            if p.place_key in places:
                places[p.place_key].merge(p)
            else:
                places[p.place_key] = p

    own = places.get(target.place_key)
    if own is not None:
        own.merge(target)
        target.merge(own)  # coordinates and type from a history entry, for free
    places[target.place_key] = target

    areas = assign_areas(AreaPoint(k, p.area, p.lat, p.lng) for k, p in places.items())
    for k, area in areas.items():
        places[k].area = area

    fetched = max((p.fetched_at for p in pages), default=db.utcnow())
    top_rated = cached_top_rated(gw, data_id)
    return AnalysisInput(
        target=target,
        target_reviews=reviews,
        places=places,
        contributors=contributors,
        histories=histories,
        expansions=expansions,
        fetched_at=fetched,
        notes=list(state.get("notes", [])),
        top_rated=top_rated,
    )


def needs_top_rated(inp: AnalysisInput) -> bool:
    """True when the displayed rating sits far above the newest reviews and the total dwarfs them."""
    cfg = config.load_tunables()["rating_gap"]
    rated = [r.rating for r in inp.target_reviews if r.rating is not None]
    displayed, total = inp.target.rating, inp.target.total_reviews
    if not rated or displayed is None or not total:
        return False
    gap = displayed - sum(rated) / len(rated)
    return gap >= cfg["min_gap"] and total >= cfg["min_total_ratio"] * len(rated)


def cached_top_rated(gw: Gateway, data_id: str) -> list:
    """The highest-rated sample, from cache only (empty when it was never fetched)."""
    out = []
    seen: set[str] = set()
    token = None
    for _ in range(int(config.tunable("rating_gap", "top_rated_pages"))):
        cached = gw.lookup_cache(catalog.top_rated_page(data_id, token))
        if cached is None:
            break
        for r in target_reviews(cached.body):
            if r.review_id not in seen:
                seen.add(r.review_id)
                out.append(r)
        token = next_page_token(cached.body)
        if not token:
            break
    return out


def cancel_analysis(analysis_id: str, conn=None) -> bool:
    conn = conn or db.connect()
    cur = conn.execute(
        "UPDATE analyses SET status = 'cancelled', finished_at = ? WHERE id = ? AND status IN "
        "('queued', 'running', 'paused', 'needs_input')",
        (db.iso(db.utcnow()), analysis_id),
    )
    return cur.rowcount > 0


def selection_for(inp: AnalysisInput) -> Selection:
    """Recompute the round-1 selection from an input (used by the evaluation harness)."""
    return selection_for_params(inp, CollectParams.from_config())


# ---------------------------------------------------------------------- estimates


@dataclass
class Estimate:
    minimum: int
    maximum: int
    lines: list[str]
    cap: int

    def as_dict(self) -> dict[str, Any]:
        return {"min": self.minimum, "max": self.maximum, "lines": self.lines, "cap": self.cap}


def estimate(resolved: ResolvedInput, params: CollectParams, db_path=None) -> Estimate:
    """Minimum and maximum searches for an analysis, using only the cache (spec 5.3)."""
    gw = Gateway(mode="offline", dry_run=True, db_path=db_path, secrets=config.Secrets(None, None))
    lines: list[str] = []
    lo = hi = 0
    data_id = resolved.data_id
    state: dict[str, Any] = {"lat": resolved.lat, "lng": resolved.lng}
    if data_id is None:
        try:
            cands = lookup(gw, resolved)
            if params.pick:
                cands = [c for c in cands if c.data_id == params.pick.lower()]
            if len(cands) == 1:
                data_id = cands[0].data_id
                state.update(lat=cands[0].lat, lng=cands[0].lng)
            lines.append("Identify the place: cached (0)")
        except NotCached:
            lo += 1
            hi += 1
            lines.append("Identify the place: 1")
    needed = pages_needed(params.n)
    pages = gw.fetch_pages(data_id, params.n) if data_id else None
    cached_pages = len(pages.responses) if pages else 0
    missing_pages = pages.missing_pages if pages else needed
    lo += missing_pages
    hi += missing_pages
    lines.append(f"Newest {params.n} reviews: {missing_pages} ({cached_pages} of {needed} pages cached)")

    k_round1 = params.k1 + params.baseline
    if pages and pages.complete and data_id:
        inp = build_input(gw, data_id, pages.responses, params.n, [], state)
        sel = selection_for_params(inp, params)
        r1 = sel.round1 + sel.baseline + sel.voice
        todo = sum(1 for c in r1 if gw.lookup_cache(catalog.contributor_history(c)) is None)
        lo += todo
        hi += todo
        lines.append(f"Round 1: {todo} of {len(r1)} reviewer histories to fetch")
        r2_max = 0 if params.stop_after_round1 else min(params.k2, len(sel.remaining))
        coords_known = inp.target.lat is not None
    else:
        lo += k_round1
        hi += k_round1 + params.voice_picks
        lines.append(f"Round 1: up to {k_round1 + params.voice_picks} reviewer histories")
        r2_max = 0 if params.stop_after_round1 else params.k2
        coords_known = resolved.lat is not None
    if r2_max:
        hi += r2_max
        lines.append(f"Round 2, only if round 1 finds overlap: up to {r2_max}")
    if pages and pages.complete and data_id and needs_top_rated(inp):
        missing_top = 0 if cached_top_rated(gw, data_id) else int(config.tunable("rating_gap", "top_rated_pages"))
        lo += missing_top
        hi += missing_top
        lines.append(f"Highest-rated sample (displayed rating far above recent reviews): {missing_top}")
    elif not (pages and pages.complete):
        hi += int(config.tunable("rating_gap", "top_rated_pages"))
        lines.append("Highest-rated sample, only if the displayed rating is far above recent reviews: 0-3")
    if not coords_known:
        hi += 1
        lines.append("Target coordinates, only if no history contains them: 0-1")
    cap = int(config.tunable("budget", "per_analysis_cap"))
    return Estimate(lo, min(hi, cap), lines, cap)


def selection_for_params(inp: AnalysisInput, params: CollectParams) -> Selection:
    features = compute_text_features(inp)
    keyword_ids = set(keyword_style(inp.target_reviews, inp.target)["review_ids"])
    cands = score_reviews(inp.target_reviews, detect_bursts(inp.target_reviews), features, keyword_ids)
    sel = select_round1(cands, inp.target.place_key, params.k1, params.baseline)
    add_voice_picks(sel, inp.target_reviews, params.voice_picks, keyword_ids)
    return sel


def add_voice_picks(sel: Selection, reviews: list, k: int, keyword_ids: set[str]) -> None:
    """Round 1 also opens the authors of long reviews, so their writing can be compared with their own."""
    if k <= 0:
        return
    sel.voice = select_voice(reviews, set(sel.round1) | set(sel.baseline), k, keyword_ids)
    sel.remaining = [c for c in sel.remaining if c.contributor_id not in set(sel.voice)]

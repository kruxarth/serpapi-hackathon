"""FastAPI app. Local only: bind to 127.0.0.1 (spec 11).

Drive-by protection: every POST/PUT needs ``X-ReviewRing: 1`` and a JSON body.
The custom header forces a CORS preflight, which is refused for any origin but
the web app's. A Host check stops DNS-rebinding pages from posing as localhost.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import ALGORITHM_VERSION, config, db, redact, settings
from ..collect import CollectParams, estimate
from ..privacy import pseudonymize_report
from ..resolve import InputRefused, ResolvedInput, candidates_from_body, lookup, lookup_request, parse_input
from ..serp.errors import GatewayError, InvalidApiKey, NoApiKey, NotCached
from ..serp.gateway import Gateway
from .jobs import JobManager

log = logging.getLogger(__name__)

WEB_DIST = config.REPO_ROOT / "web" / "dist"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class AnalysisRequest(BaseModel):
    input: str = Field(min_length=1, max_length=2000)
    n: int | None = Field(default=None, ge=8, le=208)
    k1: int | None = Field(default=None, ge=1, le=30)
    k2: int | None = Field(default=None, ge=0, le=40)
    stop_after_round1: bool = False
    pick: str | None = None
    dry_run: bool = False
    force_refresh: bool = False


class ResolveRequest(BaseModel):
    input: str = Field(min_length=1, max_length=2000)
    confirm_lookup: bool = False
    n: int | None = None
    k1: int | None = None
    k2: int | None = None
    stop_after_round1: bool = False
    pick: str | None = None


class ResumeRequest(BaseModel):
    pick: str | None = None


def default_gateway_factory(mode: str) -> Gateway:
    return Gateway(mode="live" if mode == "live" else "offline")


def create_app(
    gateway_factory: Callable[[str], Gateway] | None = None,
    *,
    extra_origins: list[str] | None = None,
) -> FastAPI:
    redact.install()
    for value in config.load_secrets().values():
        redact.register_secret(value)
    factory = gateway_factory or default_gateway_factory
    app = FastAPI(title="ReviewRing", version=ALGORITHM_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.jobs = JobManager(factory)
    app.state.account_cache = {"at": 0.0, "data": None}

    origins = list(config.tunable("server", "dev_origins")) + list(extra_origins or [])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Only installed extensions have this origin; web pages can't use it.
        allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-ReviewRing"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def require_custom_header(request: Request, call_next):
        if request.method in MUTATING and request.url.path.startswith("/api/"):
            if request.headers.get("x-reviewring") != "1":
                return JSONResponse({"detail": "Missing X-ReviewRing header."}, status_code=403)
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return JSONResponse({"detail": "Requests must be application/json."}, status_code=415)
        return await call_next(request)

    @app.exception_handler(GatewayError)
    async def gateway_error(_: Request, exc: GatewayError):
        code = 401 if isinstance(exc, (InvalidApiKey, NoApiKey)) else 409
        return JSONResponse({"detail": str(exc), "kind": type(exc).__name__}, status_code=code)

    @app.exception_handler(InputRefused)
    async def input_refused(_: Request, exc: InputRefused):
        return JSONResponse({"detail": str(exc), "kind": "InputRefused"}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        return JSONResponse({"detail": f"Internal error: {redact.safe_error(exc)}"}, status_code=500)

    def mode() -> str:
        return settings.load()["mode"]

    def present(request: Request) -> bool:
        flag = request.query_params.get("presentation")
        if flag is not None:
            return flag in ("1", "true", "yes")
        return bool(settings.load().get("presentation_mode"))

    # ------------------------------------------------------------------ status

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        s = settings.public()
        return {
            "status": "ok",
            "mode": s["mode"],
            "algorithm_version": ALGORITHM_VERSION,
            "serpapi_key_set": s["serpapi_key_set"],
            "deepseek_key_set": s["deepseek_key_set"],
        }

    @app.get("/api/budget")
    def budget() -> dict[str, Any]:
        m = mode()
        gw = factory("live" if m == "live" else "offline")
        note = None
        if m == "live":
            cache = app.state.account_cache
            if time.monotonic() - cache["at"] > 60 or cache["data"] is None:
                try:
                    cache["data"] = gw.refresh_account()
                    cache["fetched"] = db.utcnow()
                    cache["at"] = time.monotonic()
                except NoApiKey:
                    note = "No SerpApi key is set."
                except GatewayError as exc:
                    note = str(exc)
            else:
                gw.use_account(cache["data"], cache["fetched"])
        status = gw.budget_status().as_dict()
        return {**status, "mode": m, "note": note, "account": app.state.account_cache["data"] if m == "live" else None}

    # ------------------------------------------------------------------ resolve and estimate

    def _params(body: AnalysisRequest | ResolveRequest) -> CollectParams:
        return CollectParams.from_config(
            n=body.n, k1=body.k1, k2=body.k2, stop_after_round1=body.stop_after_round1 or None, pick=body.pick
        )

    @app.post("/api/resolve")
    def resolve(body: ResolveRequest) -> dict[str, Any]:
        m = mode()
        if m == "demo":
            raise HTTPException(409, "Demo mode can't analyse new places. Switch to live or offline mode.")
        resolved = parse_input(body.input)
        out: dict[str, Any] = {"resolved": {k: v for k, v in resolved.__dict__.items() if v is not None}}
        req = lookup_request(resolved)
        if req is not None:
            gw = factory("live" if m == "live" else "offline")
            cached = gw.lookup_cache(req)
            if cached is None and not body.confirm_lookup:
                out["needs_confirmation"] = True
                out["lookup_cost"] = 1
            else:
                try:
                    out["candidates"] = [c.__dict__ for c in lookup(gw, resolved)]
                except NotCached:
                    out["needs_confirmation"] = True
                    out["lookup_cost"] = 1
        out["estimate"] = estimate(resolved, _params(body)).as_dict()
        return out

    # ------------------------------------------------------------------ analyses

    @app.post("/api/analyses")
    def start(body: AnalysisRequest) -> dict[str, Any]:
        m = mode()
        if m == "demo":
            raise HTTPException(409, "Demo mode shows prepared analyses only. Switch to live or offline mode.")
        resolved = parse_input(body.input)
        params = _params(body)
        params.force_refresh = body.force_refresh
        est = estimate(resolved, params)
        if body.dry_run:
            return {"dry_run": True, "estimate": est.as_dict()}
        if m == "live":
            gw = factory("live")
            gw.refresh_account()
            status = gw.budget_status()
            if est.maximum > status.month_remaining:
                log.warning(
                    "analysis refused: up to %s searches needed, %s left this month",
                    est.maximum,
                    status.month_remaining,
                )
                raise HTTPException(
                    409,
                    "ReviewRing has reached its limit for new analyses this month. Places already analysed still "
                    "open, and the limit resets at the start of next month. (Settings shows the details.)",
                )
        analysis_id = app.state.jobs.submit(body.input, params, m)
        return {"analysis_id": analysis_id, "estimate": est.as_dict()}

    @app.get("/api/analyses")
    def list_analyses(request: Request, limit: int = 50, per_place: bool = False) -> list[dict[str, Any]]:
        """Newest first. ``per_place`` keeps only the newest analysis of each place (the home page's list)."""
        if mode() == "demo":
            from ..demo import list_demo

            return list_demo()
        rows = (
            db.connect()
            .execute(
                "SELECT id, input, status, stage, searches_used, started_at, finished_at, place_key, report "
                "FROM analyses ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (min(limit, 200),),
            )
            .fetchall()
        )
        hide = present(request)
        out = []
        seen: set[str] = set()
        for r in rows:
            if per_place and r["place_key"]:
                if r["place_key"] in seen:
                    continue
                seen.add(r["place_key"])
            report = json.loads(r["report"]) if r["report"] else None
            item = {
                "id": r["id"],
                "status": r["status"],
                "stage": r["stage"],
                "searches_used": r["searches_used"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "input": None if hide else r["input"],
                "title": None,
                "type": None,
                "area": None,
                "level": None,
            }
            if report:
                item.update(
                    title=None if hide else report["place"].get("title"),
                    type=report["place"].get("type"),
                    area=report["place"].get("area"),
                    level=report["level"]["level"],
                    adjusted=report["ratings"]["without_ring"],
                    sample_mean=report["ratings"]["sample_mean"],
                    kept_mean=report["ratings"].get("kept_mean"),
                    kept_count=report["ratings"].get("kept_count"),
                    examined=report["ratings"]["examined"],
                )
            out.append(item)
        return out

    def _row(analysis_id: str):
        row = db.connect().execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such analysis.")
        return row

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
        if mode() == "demo":
            from ..demo import get_demo

            found = get_demo(analysis_id)
            if found is None:
                raise HTTPException(404, "No such demo analysis.")
            return found
        row = _row(analysis_id)
        report = json.loads(row["report"]) if row["report"] else None
        if report is not None and present(request):
            report = pseudonymize_report(report)
        state = json.loads(row["state"] or "{}")
        return {
            "id": row["id"],
            "status": row["status"],
            "stage": row["stage"],
            "error": row["error"],
            "searches_used": row["searches_used"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "input": None if present(request) else row["input"],
            "paused": state.get("paused"),
            "candidates": [] if present(request) else state.get("candidates", []),
            "missing": state.get("missing", {}),
            "report": report,
        }

    @app.get("/api/analyses/{analysis_id}/events")
    def events(analysis_id: str) -> StreamingResponse:
        jobs: JobManager = app.state.jobs

        def stream() -> Iterator[str]:
            if not jobs.known(analysis_id):
                row = _row(analysis_id)
                yield _sse(
                    {
                        "type": row["status"],
                        "message": f"Analysis is {row['status']}.",
                        "searches_used": row["searches_used"],
                        "data": {},
                    }
                )
                return
            index = 0
            while True:
                batch, finished = jobs.events_since(analysis_id, index, timeout=15)
                for e in batch:
                    yield _sse(e)
                index += len(batch)
                if finished and not batch:
                    return
                if not batch:
                    yield ": keep-alive\n\n"

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.post("/api/analyses/{analysis_id}/resume")
    def resume(analysis_id: str, body: ResumeRequest) -> dict[str, Any]:
        row = _row(analysis_id)
        if row["status"] not in ("paused", "error", "needs_input", "cancelled", "collected"):
            raise HTTPException(409, f"Analysis is {row['status']}; nothing to resume.")
        params = CollectParams(**json.loads(row["params"])) if row["params"] else CollectParams.from_config()
        if body.pick:
            params.pick = body.pick
        m = mode()
        if m == "demo":
            raise HTTPException(409, "Switch to live or offline mode to resume.")
        app.state.jobs.submit(row["input"], params, m, analysis_id=analysis_id)
        return {"analysis_id": analysis_id}

    @app.post("/api/analyses/{analysis_id}/cancel")
    def cancel(analysis_id: str) -> dict[str, Any]:
        _row(analysis_id)
        return {"cancelled": app.state.jobs.cancel(analysis_id)}

    @app.post("/api/analyses/{analysis_id}/export")
    def export(analysis_id: str) -> dict[str, Any]:
        from ..exporter import export_analysis

        path = export_analysis(analysis_id)
        return {"fixture": path.name}

    def known_place(text: str, resolved: ResolvedInput) -> str | None:
        """The place an input without a Maps id already led to: an earlier analysis started from the same input, or
        a cached lookup that found exactly one place. Free."""
        row = (
            db.connect()
            .execute(
                "SELECT place_key FROM analyses WHERE input = ? AND place_key IS NOT NULL "
                "ORDER BY started_at DESC LIMIT 1",
                (text,),
            )
            .fetchone()
        )
        if row is not None:
            return row["place_key"]
        req = lookup_request(resolved)
        cached = factory("offline").lookup_cache(req) if req is not None else None
        found = candidates_from_body(cached.body) if cached is not None else []
        return found[0].data_id if len(found) == 1 else None

    @app.get("/api/places/latest")
    def latest(request: Request, data_id: str | None = None, url: str | None = None) -> dict[str, Any]:
        """The newest finished analysis for a place (free). Used by the extension.

        A share.google link names a place without identifying it; until a lookup has found it the reason is
        ``needs_lookup``, and checking it starts with that lookup.
        """
        query = None
        if url and not data_id:
            try:
                resolved = parse_input(url.strip())
            except InputRefused:
                return {"found": False, "reason": "no_place"}
            data_id = resolved.data_id or known_place(url.strip(), resolved)
            query = resolved.query
        if not data_id and not query:
            return {"found": False, "reason": "no_place"}
        if mode() == "demo":
            return {"found": False, "reason": "demo", "message": "Demo mode can't match real Maps pages."}
        if not data_id:
            return {"found": False, "reason": "needs_lookup", **({} if present(request) else {"query": query})}
        row = (
            db.connect()
            .execute(
                "SELECT id, finished_at, report FROM analyses WHERE place_key = ? AND status = 'done' "
                "ORDER BY finished_at DESC LIMIT 1",
                (data_id.lower(),),
            )
            .fetchone()
        )
        if row is None:
            return {"found": False, "reason": "not_analysed", "data_id": data_id.lower()}
        report = json.loads(row["report"])
        if present(request):
            report = pseudonymize_report(report)
        age = (db.utcnow() - datetime.fromisoformat(row["finished_at"])).total_seconds() / 86400
        return {"found": True, "analysis_id": row["id"], "age_days": round(age, 1), "summary": summarize(report)}

    # ------------------------------------------------------------------ evaluation and settings

    @app.get("/api/evaluation")
    def evaluation() -> dict[str, Any]:
        path = config.REPO_ROOT / "docs" / "evaluation" / "results.json"
        if not path.exists():
            return {"available": False}
        return {"available": True, **json.loads(path.read_text())}

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return settings.public()

    @app.put("/api/settings")
    def put_settings(changes: dict[str, Any]) -> dict[str, Any]:
        try:
            settings.save(changes)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return settings.public()

    # ------------------------------------------------------------------ single-process web app

    if WEB_DIST.exists():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (WEB_DIST / path).resolve()
            if path and target.is_file() and WEB_DIST.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")

    return app


HEADLINES = [  # (evidence kind, short reason for the badge), strongest first
    ("ring", "linked reviewer group"),
    ("generated_text", "chatbot text in reviews"),
    ("review_burst", "burst of same-star reviews"),
    ("keyword_style", "reviews written like search ads"),
    ("possible_ring_trip", "possible linked group"),
    ("rating_gap", "rating carried by old reviews"),
]


def headline(report: dict[str, Any]) -> str | None:
    kinds = {e["kind"] for e in report.get("evidence", [])}
    return next((text for kind, text in HEADLINES if kind in kinds), None)


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    """The extension's summary: level, main reason, ratings, sign counts and the top 3 evidence sentences."""
    order = {kind: i for i, (kind, _) in enumerate(HEADLINES)}
    evidence = sorted(report["evidence"], key=lambda e: order.get(e["kind"], len(order)))
    return {
        "level": report["level"]["level"],
        "headline": headline(report),
        "reasons": report["level"]["reasons"],
        "title": report["place"].get("title"),
        "rating": report["place"].get("rating"),
        "sample_mean": report["ratings"]["sample_mean"],
        "adjusted": report["ratings"]["without_ring"],
        "examined": report["ratings"]["examined"],
        "rings": sum(1 for g in report["groups"] if g["verdict"] in ("ring", "possible_ring", "possible_ring_trip")),
        "kept_mean": report["ratings"].get("kept_mean"),
        "kept_count": report["ratings"].get("kept_count"),
        "signs": {k: v["count"] for k, v in (report.get("sieve") or {}).get("signs", {}).items()},
        "evidence": [e["text"] for e in evidence[:3]],
    }


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def web_dist() -> Path:
    return WEB_DIST

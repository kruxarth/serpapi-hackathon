"""Export a finished analysis as a pseudonymized fixture (spec 14).

The fixture holds the normalized engine input (pseudonymized) plus the report
the engine produces from it. Demo mode re-runs the engine on the input, so a
fixture is both the demo data and a determinism test.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import ALGORITHM_VERSION, config, db
from .engine.analyze import analyze
from .engine.features import compute_text_features, history_text_id, target_text_id
from .engine.target_signals import generated_marker
from .leakcheck import check_object, originals_from_cache
from .model import AnalysisInput, Contributor, Expansion, HistoryReview, Place, TargetReview
from .normalize.text import TextFeatures
from .privacy import (
    TEXT_KEEP_CHARS,
    TEXT_KEEP_MIN_ACCOUNTS,
    approx_count,
    date_offset_days,
    hashed,
    letters,
    round1,
    salt,
    scrub_text,
)

FIXTURE_VERSION = 1
FIXTURES_DIR = config.REPO_ROOT / "fixtures"


class LeakFound(RuntimeError):
    def __init__(self, findings) -> None:
        super().__init__(f"Export blocked by the leak check: {len(findings)} finding(s)")
        self.findings = findings


def _r1(v: float | None) -> float | None:
    return round1(v)


def pseudonymize_input(inp: AnalysisInput, salt_value: str) -> AnalysisInput:
    """Hash ids, rename businesses, reduce addresses to areas, round coordinates, drop most text."""
    features = compute_text_features(inp)

    def pk(key: str | None) -> str | None:
        return None if key is None else hashed(key, "p", salt_value)

    def uid(cid: str | None) -> str | None:
        return None if cid is None else hashed(cid, "u", salt_value)

    def rid(r: str) -> str:
        return hashed(r, "r", salt_value)

    cluster_map: dict[str, str] = {}
    for c in sorted(
        {f.cluster for f in features.values() if f.cluster}
        | {f.target_cluster for f in features.values() if f.target_cluster}
    ):
        cluster_map[c] = f"c{len(cluster_map) + 1}"
    accounts: dict[str, set[str]] = {}
    for f in features.values():
        if f.cluster:
            accounts.setdefault(f.cluster, set()).add(f.owner or f.text_id)

    title_words = {w for w in re.split(r"\W+", inp.target.title or "") if len(w) >= 4}
    for p in inp.places.values():
        if p.title and p.place_key != inp.target.place_key:
            title_words |= {w for w in re.split(r"\W+", p.title) if len(w) >= 5}

    def text_for(tid: str, text: str | None) -> str | None:
        f = features.get(tid)
        if not text or not f or not f.cluster or len(accounts.get(f.cluster, ())) < TEXT_KEEP_MIN_ACCOUNTS:
            return None
        return scrub_text(text, title_words)[:TEXT_KEEP_CHARS]

    order = [inp.target.place_key] + sorted(k for k in inp.places if k != inp.target.place_key)
    names = {k: letters(i) for i, k in enumerate(order)}

    def place(p: Place) -> Place:
        label = f"{p.type} {names[p.place_key]}" if p.type else f"Business {names[p.place_key]}"
        return Place(
            pk(p.place_key), None, label, None, _r1(p.lat), _r1(p.lng), p.type, p.area, p.rating, p.total_reviews
        )

    target = place(inp.target)
    target.total_reviews = approx_count(target.total_reviews)
    shift = timedelta(days=date_offset_days(salt_value, inp.target.place_key))

    def dt(v):
        return None if v is None else v - shift

    def shifted_images(dates: list[str]) -> list[str]:
        out = []
        for d in dates:
            try:
                out.append((date.fromisoformat(d[:10]) - shift).isoformat())
            except ValueError:
                continue
        return out

    places = {pk(k): place(p) for k, p in inp.places.items()}
    reviews = [
        TargetReview(
            rid(r.review_id),
            uid(r.contributor_id),
            r.rating,
            dt(r.posted_at),
            r.edited,
            text_for(target_text_id(r.review_id), r.text),
            r.has_images,
            r.reviewer_reviews,
            r.reviewer_photos,
            r.local_guide,
            None,
        )
        for r in inp.target_reviews
    ]
    contributors = {
        uid(cid): Contributor(
            uid(cid),
            None,
            c.level,
            c.points,
            c.local_guide,
            {k: v for k, v in c.contributions.items() if isinstance(v, int)},
            c.reviews_returned,
            c.truncated,
            c.status,
            dt(c.fetched_at),
        )
        for cid, c in inp.contributors.items()
    }
    histories = {
        uid(cid): [
            HistoryReview(
                uid(cid),
                rid(h.review_id),
                pk(h.place_key),
                h.rating,
                h.relative_date,
                dt(h.date_min),
                dt(h.date_max),
                h.edited,
                shifted_images(h.image_dates),
                None if h.place_key == inp.target.place_key else text_for(history_text_id(cid, h.review_id), h.text),
                h.travel_group,
            )
            for h in hs
        ]
        for cid, hs in inp.histories.items()
    }
    new_features: dict[str, TextFeatures] = {}
    for tid, f in features.items():
        if tid.startswith("t:"):
            new_tid = target_text_id(rid(tid[2:]))
        else:
            _, cid, r = tid.split(":", 2)
            new_tid = history_text_id(uid(cid), rid(r))
        new_features[new_tid] = TextFeatures(
            new_tid,
            uid(f.owner),
            f.length,
            f.script,
            f.short,
            cluster_map.get(f.cluster) if f.cluster else None,
            cluster_map.get(f.target_cluster) if f.target_cluster else None,
        )
    return AnalysisInput(
        target=target,
        target_reviews=reviews,
        places=places,
        contributors=contributors,
        histories=histories,
        expansions=[Expansion(uid(e.contributor_id), e.round, e.reason) for e in inp.expansions],
        fetched_at=dt(inp.fetched_at),
        params=dict(inp.params),
        text_features=new_features,
        notes=list(inp.notes),
        top_rated=[
            TargetReview(
                rid(r.review_id),
                uid(r.contributor_id),
                r.rating,
                dt(r.posted_at),
                r.edited,
                None,
                r.has_images,
                r.reviewer_reviews,
                r.reviewer_photos,
                r.local_guide,
                None,
                generated_marker(r),
            )
            for r in inp.top_rated
        ],
    )


# ---------------------------------------------------------------------- (de)serialization


def _json_default(o: Any):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(type(o))


def input_to_dict(inp: AnalysisInput) -> dict[str, Any]:
    return {
        "target": asdict(inp.target),
        "target_reviews": [asdict(r) for r in inp.target_reviews],
        "places": {k: asdict(p) for k, p in sorted(inp.places.items())},
        "contributors": {k: asdict(c) for k, c in sorted(inp.contributors.items())},
        "histories": {k: [asdict(h) for h in hs] for k, hs in sorted(inp.histories.items())},
        "expansions": [asdict(e) for e in inp.expansions],
        "fetched_at": inp.fetched_at,
        "params": inp.params,
        "text_features": {k: asdict(f) for k, f in sorted((inp.text_features or {}).items())},
        "notes": inp.notes,
        "top_rated": [asdict(r) for r in inp.top_rated],
    }


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def input_from_dict(d: dict[str, Any]) -> AnalysisInput:
    return AnalysisInput(
        target=Place(**d["target"]),
        target_reviews=[TargetReview(**{**r, "posted_at": _dt(r["posted_at"])}) for r in d["target_reviews"]],
        places={k: Place(**p) for k, p in d["places"].items()},
        contributors={
            k: Contributor(**{**c, "fetched_at": _dt(c["fetched_at"])}) for k, c in d["contributors"].items()
        },
        histories={
            k: [HistoryReview(**{**h, "date_min": _d(h["date_min"]), "date_max": _d(h["date_max"])}) for h in hs]
            for k, hs in d["histories"].items()
        },
        expansions=[Expansion(**e) for e in d["expansions"]],
        fetched_at=_dt(d["fetched_at"]),  # type: ignore[arg-type]
        params=d.get("params", {}),
        text_features={k: TextFeatures(**f) for k, f in d.get("text_features", {}).items()} or None,
        notes=d.get("notes", []),
        top_rated=[TargetReview(**{**r, "posted_at": _dt(r["posted_at"])}) for r in d.get("top_rated", [])],
    )


def build_fixture(
    inp: AnalysisInput,
    slug: str,
    *,
    title: str,
    synthetic: bool = False,
    ai_summary: dict[str, Any] | None = None,
    salt_value: str | None = None,
) -> dict[str, Any]:
    pseudo = pseudonymize_input(inp, salt_value if salt_value is not None else salt())
    report = analyze(pseudo)
    fixture = {
        "fixture_version": FIXTURE_VERSION,
        "slug": slug,
        "title": title,
        "synthetic": synthetic,
        "algorithm_version": ALGORITHM_VERSION,
        "input": input_to_dict(pseudo),
        "report": report,
    }
    if ai_summary:
        fixture["ai_summary"] = ai_summary
    return json.loads(json.dumps(fixture, default=_json_default))


def write_fixture(fixture: dict[str, Any], *, originals=None, directory: Path | None = None) -> Path:
    findings = check_object(fixture, fixture["slug"], originals_from_cache() if originals is None else originals)
    if findings:
        raise LeakFound(findings)
    directory = directory or FIXTURES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{fixture['slug']}.json"
    path.write_text(json.dumps(fixture, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    return path


def export_analysis(analysis_id: str, slug: str | None = None, title: str | None = None) -> Path:
    """Rebuild the analysis input from the cache (0 searches), pseudonymize, check and write it."""
    from .collect import Collector, CollectParams
    from .serp.gateway import Gateway

    conn = db.connect()
    row = conn.execute("SELECT input, params, status, report FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    if row is None:
        raise ValueError(f"No analysis {analysis_id}")
    params = CollectParams(**json.loads(row["params"])) if row["params"] else CollectParams.from_config()
    outcome = Collector(Gateway(mode="offline"), row["input"], params, analysis_id=analysis_id).run()
    if outcome.status != "done" or outcome.input is None:
        raise ValueError(f"Analysis {analysis_id} can't be rebuilt from the cache: {outcome.message}")
    conn.execute("UPDATE analyses SET status = 'done' WHERE id = ?", (analysis_id,))
    report = json.loads(row["report"]) if row["report"] else {}
    ai = report.get("ai_summary")
    level = report.get("level", {}).get("level", "")
    slug = slug or f"case-{analysis_id[:6]}"
    title = title or f"{outcome.input.target.type or 'Business'} ({level or 'analysis'})"
    return write_fixture(build_fixture(outcome.input, slug, title=title, ai_summary=ai))

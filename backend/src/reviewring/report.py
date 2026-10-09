"""Finish an analysis: run the engine, attach metadata, store the report."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from . import config, db, settings
from .engine.analyze import LABEL_TEXT, analyze
from .llm import LLMGateway, LLMRefused, judge_texts, judge_voices, paraphrase_groups, summarize
from .model import AnalysisInput
from .privacy import business_terms
from .serp.gateway import Gateway
from .store import save_parsed

log = logging.getLogger(__name__)


def build_report(
    analysis_id: str, inp: AnalysisInput, mode: str, conn=None, paraphrase: dict[str, int] | None = None
) -> dict[str, Any]:
    conn = conn or db.connect()
    report = analyze(inp, paraphrase_groups=paraphrase)
    row = conn.execute(
        "SELECT input, params, started_at, searches_used, state FROM analyses WHERE id = ?", (analysis_id,)
    ).fetchone()
    state = json.loads(row["state"] or "{}") if row else {}
    used = conn.execute(
        "SELECT COUNT(*) FROM ledger WHERE analysis_id = ? AND status IN ('ok', 'empty')", (analysis_id,)
    ).fetchone()[0]
    budget = Gateway(mode="offline").budget_status().as_dict()
    report["analysis"] = {
        "id": analysis_id,
        "mode": mode,
        "params": json.loads(row["params"]) if row and row["params"] else inp.params,
        "searches_used": used,
        "started_at": row["started_at"] if row else None,
        "finished_at": db.iso(db.utcnow()),
        "early_stop": state.get("early_stop"),
        "missing": state.get("missing", {}),
        "coords_source": state.get("coords_source"),
    }
    names: dict[str, str] = {}
    for r in inp.target_reviews:
        if r.contributor_id and r.reviewer_name:
            names[r.contributor_id] = r.reviewer_name
    for cid, c in inp.contributors.items():
        if c.name:
            names[cid] = c.name
    report["names"] = names  # local only; stripped by pseudonymization
    report["budget"] = {k: budget[k] for k in ("month_remaining", "hour_remaining", "monthly_cap", "hourly_cap")}
    selection = state.get("selection") or {}
    ranked_not_checked = max(0, int(selection.get("candidates", 0)) - len(inp.expansions))
    report["sample"]["not_checked_high_priority"] = ranked_not_checked
    return report


def store_report(
    analysis_id: str, inp: AnalysisInput, mode: str, on_progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    """Build the report, add the AI opinions and summary (validated LLM text or templates) and store it.

    Live mode may call the LLM when a key is set; offline and demo modes only reuse cached replies.
    """
    conn = db.connect()
    llm = LLMGateway(mode="live" if mode == "live" else "offline")
    texts = {r.review_id: r.text for r in inp.target_reviews if r.text}
    words = business_terms(inp.target.title)
    if texts and not inp.text_judgements and config.load_tunables()["ai_text"].get("enabled", True):
        if on_progress and llm.can_call:
            on_progress("Reading the longer reviews for AI-written style")
        inp.text_judgements = judge_texts(texts, llm, words)
    if inp.expansions and not inp.voice_judgements and config.tunable("voice", "enabled"):
        if on_progress and llm.can_call:
            on_progress("Comparing reviewers' writing with their other reviews")
        inp.voice_judgements = judge_voices(inp, llm, words)
    paraphrase = None
    if settings.load().get("paraphrase_signal"):
        try:
            paraphrase = paraphrase_groups(texts, llm, words)
        except (LLMRefused, RuntimeError) as exc:
            log.warning("paraphrase signal skipped: %s", exc)
    save_parsed(inp, conn)
    report = build_report(analysis_id, inp, mode, conn, paraphrase)
    try:
        report["ai_summary"] = summarize(report, llm)
    except LLMRefused as exc:
        log.warning("AI summary refused: %s", exc)
        report["ai_summary"] = summarize(report, None)
    conn.execute(
        "UPDATE analyses SET status = 'done', stage = 'done', finished_at = ?, report = ?, place_key = ? WHERE id = ?",
        (report["analysis"]["finished_at"], json.dumps(report, default=str), inp.target.place_key, analysis_id),
    )
    return report


def finish_analysis(analysis_id: str, inp: AnalysisInput, mode: str) -> dict[str, Any]:
    report = store_report(analysis_id, inp, mode)
    print_summary(report)
    return report


def print_summary(report: dict[str, Any]) -> None:
    lvl = report["level"]
    r = report["ratings"]
    place = report["place"]
    print()
    print(
        f"== {place.get('title') or place['place_key']} ({place.get('type') or 'unknown type'}, "
        f"{place.get('area') or 'unknown area'})"
    )
    print(f"Suspicion level: {lvl['level']}")
    for reason in lvl["reasons"]:
        print(f"  - {reason}")
    print(
        f"Latest {r['examined']} reviews: {r['sample_mean']} -> {r['without_ring']} excluding linked reviewers "
        f"({r['without_ring_and_suspicious']} also without suspicious and possible-ring reviews)"
    )
    sieve = report.get("sieve") or {}
    if sieve:
        signs = ", ".join(f"{v['name']} {v['count']}" for v in sieve["signs"].values() if v["count"])
        print(f"Warning signs: {signs or 'none'}")
        print(
            f"Without the strong signs: {sieve['kept']['count']} reviews averaging {sieve['kept']['mean']} "
            f"(AI-text opinion on {sieve['ai']['judged']} of {sieve['ai']['eligible']} long-enough reviews)"
        )
    if r["overall"]:
        o = r["overall"]
        change = "no visible change overall" if o["no_visible_change"] else f"{o['low']}-{o['high']} overall"
        print(f"Displayed {o['displayed']} over {o['total_as_displayed']} reviews (as displayed): {change}")
    print("Labels: " + ", ".join(f"{LABEL_TEXT[k]} {v}" for k, v in report["label_counts"].items() if v))
    for g in report["groups"]:
        m = g["metrics"]
        conf = f", evidence strength {g['confidence']:.2f}" if g["confidence"] is not None else ""
        print(
            f"Group {g['group_id']}: {g['verdict']} - {m['size']} members, density {m['density']}, "
            f"{m['core_places']} core places, far areas {m['far_areas']}{conf}"
        )
    for e in report["evidence"]:
        print(f"* {e['text']}")
    for w in report["warnings"]:
        print(f"! {w}")
    a = report.get("analysis", {})
    if a:
        print(f"Searches used: {a.get('searches_used')}")

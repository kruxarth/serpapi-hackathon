"""Demo mode: committed pseudonymized fixtures, re-run through the engine, served by the same API.

Needs no keys and no network, so it works on a fresh clone.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .engine.analyze import analyze
from .exporter import FIXTURES_DIR, input_from_dict

_lock = threading.Lock()
_cache: dict[Path, tuple[float, dict[str, Any]]] = {}


def _load(path: Path) -> dict[str, Any]:
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    fixture = json.loads(path.read_text(encoding="utf-8"))
    report = analyze(input_from_dict(fixture["input"]))
    report["analysis"] = {
        "id": f"demo-{fixture['slug']}",
        "mode": "demo",
        "params": fixture["input"].get("params", {}),
        "searches_used": 0,
        "started_at": None,
        "finished_at": None,
        "early_stop": None,
        "missing": {},
    }
    if fixture.get("ai_summary"):
        report["ai_summary"] = fixture["ai_summary"]
    else:
        from .llm import summarize

        report["ai_summary"] = summarize(report, None)  # templates; demo mode never calls an LLM
    report["pseudonymized"] = True
    entry = {"fixture": fixture, "report": report}
    with _lock:
        _cache[path] = (mtime, entry)
    return entry


def fixture_paths(directory: Path | None = None) -> list[Path]:
    d = directory or FIXTURES_DIR
    return sorted(d.glob("*.json")) if d.exists() else []


def list_demo(directory: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for path in fixture_paths(directory):
        entry = _load(path)
        f, r = entry["fixture"], entry["report"]
        out.append(
            {
                "id": f"demo-{f['slug']}",
                "status": "done",
                "stage": "done",
                "searches_used": 0,
                "started_at": None,
                "finished_at": None,
                "input": None,
                "title": f.get("title"),
                "synthetic": bool(f.get("synthetic")),
                "type": r["place"].get("type"),
                "area": r["place"].get("area"),
                "level": r["level"]["level"],
                "adjusted": r["ratings"]["without_ring"],
                "sample_mean": r["ratings"]["sample_mean"],
                "kept_mean": r["ratings"].get("kept_mean"),
                "kept_count": r["ratings"].get("kept_count"),
                "examined": r["ratings"]["examined"],
            }
        )
    order = {"High": 0, "Elevated": 1, "Low": 2, "Not enough history": 3}
    out.sort(key=lambda x: (x["synthetic"], order.get(x["level"], 9), x["id"]))
    return out


def get_demo(analysis_id: str, directory: Path | None = None) -> dict[str, Any] | None:
    for path in fixture_paths(directory):
        entry = _load(path)
        if f"demo-{entry['fixture']['slug']}" == analysis_id:
            return {
                "id": analysis_id,
                "status": "done",
                "stage": "done",
                "error": None,
                "searches_used": 0,
                "input": None,
                "paused": None,
                "candidates": [],
                "missing": {},
                "synthetic": bool(entry["fixture"].get("synthetic")),
                "report": entry["report"],
            }
    return None

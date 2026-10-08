"""The home page's story, from real analyses: numbers only, nothing that names a business or a person.

Writes ``web/src/story/data.json`` from three stored analyses (a hotel whose rating is carried by old reviews,
a mover with a burst of first-time accounts, a mover with no strong signs). Kept: star ratings, sign keys, day
offsets between reviews (never calendar dates), counts, averages, city names, coordinates rounded to 1 decimal,
and the chatbot excerpt scrubbed of the business's name. Dropped: ids, names, titles, review texts, dates.
The output passes the same leak check as the fixtures.

    uv run python -m reviewring.story_data <hotel_id> <mover_id> <clean_id> <scripted_id> [research_keyword.json]

The optional JSON lists, per research listing, its city, reviews with text and accounts writing like search ads
(labels only, no names): the comparison chart on the home page.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from . import config, db
from .leakcheck import check_object, originals_from_cache
from .privacy import approx_count, round1, scrub_text

OUT = config.REPO_ROOT / "web" / "src" / "story" / "data.json"


def _report(analysis_id: str) -> dict[str, Any]:
    row = db.connect().execute("SELECT report FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    if row is None or not row["report"]:
        raise SystemExit(f"No finished analysis {analysis_id}")
    return json.loads(row["report"])


def _days(report: dict[str, Any]) -> list[int]:
    """Each review's age in days relative to the newest one (intervals only)."""
    days = [date.fromisoformat(r["day"]) if r.get("day") else None for r in report["reviews"]]
    newest = max(d for d in days if d)
    return [(newest - d).days if d else -1 for d in days]


def _words(report: dict[str, Any]) -> set[str]:
    return {w for w in re.split(r"\W+", report["place"].get("title") or "") if len(w) >= 4}


def chatbot_excerpt(text: str, business_words: set[str]) -> str:
    """The pasted chatbot reply up to its rating line, with the business's name (and any cut-off part of it) removed."""
    text = " ".join(text.split())
    cut = text.find("**Overall Experience")
    text = (text[:cut] if cut > 0 else text[:200]).strip()
    for word in business_words:  # a truncated excerpt can end in part of the name
        text = re.sub(rf"(?<!\w){re.escape(word[:4])}\w*", "[business]", text, flags=re.IGNORECASE)
    text = scrub_text(text, business_words)
    text = re.sub(r"(\[business\]\s*)+", "[the hotel] ", text)
    text = re.sub(r"\s*---\s*", "\n---\n", text)  # the template's own line breaks, which the API flattens
    return re.sub(r"\s*\*\*\s*\*\*\s*", "**\n**", text.replace("[the hotel] **", "[the hotel]**")).strip()


def hotel(report: dict[str, Any]) -> dict[str, Any]:
    t7, t8, ai = report["signals"]["T7"], report["signals"]["T8"], report["sieve"]["ai"]
    chatbot = (t8.get("generated") or [{}])[0].get("excerpt") or ""
    spree = None
    for rev in report["reviewers"]:
        badge = next((b for b in rev["badges"] if b["code"] == "A9"), None)
        history = report.get("histories", {}).get(rev["contributor_id"])
        if badge is None or history is None:
            continue
        start, end = badge["from"], badge["to"]
        items = []
        first = min((i["day"] for i in history["items"] if i["day"]), default=None)
        for it in history["items"]:
            if not it["day"]:
                continue
            items.append(
                {
                    "area": it["area"],
                    "lat": round1(it["lat"]),
                    "lng": round1(it["lng"]),
                    "rating": it["rating"],
                    "type_group": it["type_group"],
                    "this": it["this"],
                    "in_window": start <= it["day"] <= end,
                    "day": (date.fromisoformat(it["day"]) - date.fromisoformat(first)).days if first else None,
                }
            )
        spree = {"places": badge["places"], "areas": badge["areas"], "visible": history["visible"], "items": items}
        break
    ai_rows = [r for r in report["reviews"] if (r.get("ai") or {}).get("verdict") == "ai_style"]
    return {
        "type": report["place"]["type"],
        "area": report["place"]["area"],
        "shown": t7["displayed"],
        "total_approx": approx_count(t7["total"]),
        "ratings": [r["rating"] for r in report["reviews"]],
        "days": _days(report),
        "mean": t7["recent_mean"],
        "older_mean": t7["older_implied_mean"],
        "top": {
            "count": t8["count"],
            "window": t8["window_count"],
            "months": t8["window_months"],
            "first_time_share": t8["single_use_share"],
        },
        "chatbot": chatbot_excerpt(chatbot, _words(report)),
        "ai": {"judged": ai["judged"], "ai_style": len(ai_rows), "ratings": sorted(r["rating"] for r in ai_rows)},
        "spree": spree,
    }


def mover(report: dict[str, Any]) -> dict[str, Any]:
    burst = next(b for b in report["signals"]["T6"]["single_use_bursts"] if b["flagged"])
    ai_rows = [r for r in report["reviews"] if (r.get("ai") or {}).get("verdict") == "ai_style"]
    return {
        "type": report["place"]["type"],
        "area": report["place"]["area"],
        "shown": report["place"]["rating"],
        "total_approx": approx_count(report["place"]["total_reviews"]),
        "reviews": [{"rating": r["rating"], "signs": r.get("signs", [])} for r in report["reviews"]],
        "days": _days(report),
        "mean": report["ratings"]["sample_mean"],
        "kept_mean": report["ratings"]["kept_mean"],
        "kept": report["ratings"]["kept_count"],
        "burst": {
            "count": burst["count"],
            "first_time": burst["single_use"],
            "days": (date.fromisoformat(burst["end"]) - date.fromisoformat(burst["start"])).days + 1,
        },
        "ai": {
            "judged": report["sieve"]["ai"]["judged"],
            "ai_style": len(ai_rows),
            "first_time": sum(1 for r in ai_rows if (r.get("reviewer_reviews") or 0) <= 2),
            "ratings": sorted(r["rating"] for r in ai_rows),
        },
        "first_time_accounts": report["sieve"]["signs"]["first_time_account"]["count"],
    }


def clean(report: dict[str, Any]) -> dict[str, Any]:
    strong = [k for k, v in report["sieve"]["signs"].items() if v["count"] and v["set_aside_by_default"]]
    return {
        "area": report["place"]["area"],
        "level": report["level"]["level"],
        "mean": report["ratings"]["sample_mean"],
        "strong_signs": len(strong),
        "first_time_accounts": report["sieve"]["signs"]["first_time_account"]["count"],
        "waves": sum(1 for b in report["signals"]["T1"]["bursts"]),
        "histories": report["sample"]["histories_ok"],
        "voice_compared": (report["sieve"].get("voice") or {}).get("compared", 0),
        "voice_same": (report["sieve"].get("voice") or {}).get("same_voice", 0),
    }


def scripted(report: dict[str, Any]) -> dict[str, Any]:
    """The search-ad listing: counts, its phrases with the name and neighbourhood replaced, and the clearest voice pair
    as the two short phrases the AI quoted (never the reviewer's whole text)."""
    from .engine.textstyle import name_tokens, place_tokens
    from .model import Place

    p = report["place"]
    place = Place(p["place_key"], title=p.get("title"), area=p.get("area"))
    names = name_tokens(place) - {"packers", "movers", "and", "hotel"}
    city = {w.casefold() for w in (p.get("area") or "").split()}
    areas = place_tokens(Place("x", address=None, area=p.get("area")))  # the city and its aliases only

    def anon(phrase: str) -> str:
        out = []
        for w in phrase.split():
            if w in names:
                w = "[name]"
            elif w not in city and w not in areas and w not in {"packers", "movers", "and", "in", "of", "at", "the"}:
                w = "[area]"
            if not (out and out[-1] == w and w.startswith("[")):
                out.append(w)
        return " ".join(out)

    t10 = report["signals"]["T10"]
    signs = report["sieve"]["signs"]
    pair = next(
        (r["voice"] for r in report["reviews"] if (r.get("voice") or {}).get("verdict") == "different_voice"), None
    )
    words = _words(report)
    return {
        "area": p.get("area"),
        "shown": p.get("rating"),
        "total_approx": approx_count(p.get("total_reviews")),
        "mean": report["ratings"]["sample_mean"],
        "kept": report["ratings"]["kept_count"],
        "kept_mean": report["ratings"]["kept_mean"],
        "keyword_accounts": t10["accounts"],
        "with_text": t10["with_text"],
        "phrases": sorted({anon(k) for k in t10["phrases"]}),
        "signs": {k: v["count"] for k, v in signs.items() if v["count"]},
        "voice": {
            "compared": report["sieve"]["voice"]["compared"],
            "different": report["sieve"]["voice"]["different_voice"],
            "here": scrub_text(pair["here"], words) if pair else "",
            "elsewhere": scrub_text(pair["elsewhere"], words) if pair else "",
        },
    }


def build(hotel_id: str, mover_id: str, clean_id: str, scripted_id: str, research: str | None = None) -> dict[str, Any]:
    data = {
        "note": "Generated by reviewring.story_data from real analyses. Numbers only: no names, ids, texts or dates.",
        "hotel": hotel(_report(hotel_id)),
        "mover": mover(_report(mover_id)),
        "clean": clean(_report(clean_id)),
        "scripted": scripted(_report(scripted_id)),
    }
    if research:
        rows = json.loads(Path(research).read_text())
        data["research"] = [{k: r[k] for k in ("label", "city", "with_text", "keyword_accounts")} for r in rows]
    return data


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        print(__doc__)
        return 2
    data = build(*argv)
    findings = check_object(data, "story", originals_from_cache())
    if findings:
        for f in findings:
            print(f"leak: {f}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(config.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

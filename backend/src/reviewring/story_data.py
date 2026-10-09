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
from .privacy import TEXT_KEEP_MIN_ACCOUNTS, approx_count, business_terms, round1, scrub_text

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
    return business_terms(report["place"].get("title"))


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
    t7, t8 = report["signals"]["T7"], report["signals"]["T8"]
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
        "spree": spree,
    }


def mover(report: dict[str, Any]) -> dict[str, Any]:
    burst = next(c for c in report["signals"]["T11"]["clusters"] if c["flagged"] and c["stars"] == 5)
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
            "first_time": burst["first_time"],
            "minutes": round(burst["minutes"]),
            "core": burst["core"]["count"],
            "core_minutes": round(burst["core"]["minutes"]),
            "share": burst["share"],
            "usual_every_days": round(1 / burst["usual_per_day"]) if burst["usual_per_day"] else None,
            "offsets": burst["offsets"],
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
    }


def scripted(report: dict[str, Any]) -> dict[str, Any]:
    """The search-ad listing: counts, and its phrases with the name and neighbourhood replaced, split into ad copy
    (set aside) and reviews that only name the business with its area (kept unless the reader chooses)."""
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

    def top(sign: str, k: int) -> list[str]:
        counts: dict[str, int] = {}
        for r in report["reviews"]:
            if sign in r["signs"] and r.get("keyword_phrase"):
                ph = anon(r["keyword_phrase"])
                counts[ph] = counts.get(ph, 0) + 1
        return [ph for ph, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

    # Copied text, shown as the template behind it, never as anyone's review: the sentences two or more copies
    # share, with the words that differ as blanks, plus a misspelling several accounts at the listing share.
    clusters: dict[str, list[dict[str, Any]]] = {}
    for r in report["reviews"]:
        if "copied_text" in r["signs"] and r.get("cluster") and r.get("text"):
            clusters.setdefault(r["cluster"], []).append(r)
    words, area = business_terms(p.get("title")), set(p.get("locality") or [])
    shared = [
        rows
        for rows in clusters.values()
        if len({r["contributor_id"] or r["review_id"] for r in rows}) >= TEXT_KEEP_MIN_ACCOUNTS
    ]
    shared.sort(key=lambda rows: (-sum((r["reviewer_reviews"] or 0) <= 1 for r in rows), -len(rows)))
    template = None
    if shared:
        rows = shared[0]
        scrub = lambda t: " ".join(scrub_text(t, words, area).split())  # noqa: E731
        texts = [scrub(r["text"]) for r in rows]
        listing = [(r["contributor_id"] or r["review_id"], scrub(r["text"])) for r in report["reviews"] if r["text"]]
        days = sorted(r["day"] for r in rows if r.get("day"))
        template = {
            **copy_template(texts, listing, {w.casefold() for w in re.findall(r"\w+", p.get("area") or "")}),
            "accounts": len(rows),
            "first_time": sum((r["reviewer_reviews"] or 0) <= 1 for r in rows),
            "five_star": sum(r["rating"] == 5 for r in rows),
            "months": round((date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days / 30.4) if days else 0,
        }

    aside = set(report["sieve"]["set_aside_by_default"]) | {"names_area"}
    stricter = [r["rating"] for r in report["reviews"] if not aside & set(r["signs"]) and r["rating"] is not None]
    return {
        "area": p.get("area"),
        "shown": p.get("rating"),
        "total_approx": approx_count(p.get("total_reviews")),
        "mean": report["ratings"]["sample_mean"],
        "kept": report["ratings"]["kept_count"],
        "kept_mean": report["ratings"]["kept_mean"],
        "keyword_accounts": t10["accounts"],
        "with_text": t10["with_text"],
        "ads": t10["ads"],
        "ad_phrases": [ph for ph in top("keyword_style", 8) if "[name]" not in ph][:3],  # the bare search term
        "name_phrases": top("names_area", 3),
        "phrases": sorted(set(top("keyword_style", 4) + top("names_area", 3))),
        "signs": {k: v["count"] for k, v in signs.items() if v["count"]},
        "copies": {
            "count": signs.get("copied_text", {}).get("count", 0),
            "templates": len(clusters),
            "template": template,
        },
        "kept_named": len(stricter),
        "kept_named_mean": round(sum(stricter) / len(stricter), 2) if stricter else None,
    }


_WORD = re.compile(r"\[\w+\]|[^\W_]+(?:'[^\W_]+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|,\s+(?=I\b)")
DICTIONARY = Path("/usr/share/dict/cracklib-small")


def copy_template(texts: list[str], listing: list[tuple[str, str]], places: set[str]) -> dict[str, Any]:
    """The template behind near-identical reviews: the sentences of the most typical copy that the others share,
    with the words they don't share as blanks (None), and a misspelling written by several accounts at the listing.

    Words come back as [text, kind] pairs: kind is "word", "blank", "slot" (a hidden name or place) or "typo".
    """

    def toks(t: str) -> list[str]:
        return _WORD.findall(t)

    sents = [[toks(x) for x in _SENTENCE.split(t) if x.strip()] for t in texts]

    def sim(a: list[str], b: list[str]) -> float:
        sa, sb = {w.casefold() for w in a}, {w.casefold() for w in b}
        return len(sa & sb) / max(1, len(sa | sb))

    def typical(i: int) -> float:
        return sum(max((sim(x, o) for o in sents[j]), default=0) for x in sents[i] for j in range(len(sents)) if j != i)

    known = set(DICTIONARY.read_text().split()) if DICTIONARY.exists() else None
    typo = None
    if known is not None:  # a rare non-word in the copies, written by 2+ accounts at the listing
        odd = {w.casefold() for t in texts for w in toks(t) if w.isalpha() and w.casefold() not in known | places}
        by: dict[str, set[str]] = {}
        written: dict[str, dict[str, int]] = {}
        for who, t in listing:
            ws = toks(t)
            for i, w in enumerate(ws):
                if w.casefold() in odd:
                    by.setdefault(w.casefold(), set()).add(who)
                    as_written = f"{ws[i - 1]} {w}" if i and not ws[i - 1].startswith("[") else w
                    written.setdefault(w.casefold(), {}).setdefault(as_written.casefold(), 0)
                    written[w.casefold()][as_written.casefold()] += 1
        rare = [kv for kv in by.items() if 2 <= len(kv[1]) <= max(5, len(listing) // 10)]
        best = max(rare, key=lambda kv: len(kv[1]), default=None)
        if best:
            forms = sorted(written[best[0]].items(), key=lambda kv: -kv[1])
            typo = {"word": best[0], "accounts": len(best[1]), "written": [f for f, _ in forms[:3]]}

    m = max(range(len(texts)), key=typical)
    lines = []
    for x in sents[m]:
        matches = [max(sents[j], key=lambda o: sim(x, o)) for j in range(len(sents)) if j != m]
        matches = [o for o in matches if sim(x, o) >= 0.4]
        if not matches:
            continue
        line: list[list[str]] = []
        for w in x:
            shared = sum(w.casefold() in {v.casefold() for v in o} for o in matches) * 2 >= len(matches)
            kind = "slot" if w.startswith("[") else "typo" if typo and w.casefold() == typo["word"] else "word"
            if not shared and kind == "word":
                if not (line and line[-1][1] == "blank"):
                    line.append(["", "blank"])
                continue
            if kind == "slot" and line and line[-1] == [w, "slot"]:
                continue
            line.append([w, kind])
        lines.append({"words": line, "copies": 1 + len(matches)})
    return {"lines": lines, "typo": typo}


def _input(analysis_id: str):
    """A stored analysis rebuilt from the cache with its reviewer histories (offline, 0 searches): texts the report
    leaves out."""
    from .collect import build_input
    from .model import Expansion
    from .serp.gateway import Gateway

    row = db.connect().execute("SELECT state FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    state = json.loads(row["state"])
    sel = state.get("selection") or {}
    cids = [*sel.get("round1", []), *sel.get("baseline", []), *sel.get("voice", []), *sel.get("round2", [])]
    gw = Gateway(mode="offline", dry_run=True)
    pages = gw.fetch_pages(state["data_id"], 100)
    return build_input(gw, state["data_id"], pages.responses, 100, [Expansion(c, 1, "priority") for c in cids], state)


def _runs(a: str, b: str, n: int = 3) -> list[bool]:
    """For each word of `a`: is it inside a run of `n`+ words that also occurs, in order, in `b`?"""
    wa, wb = [w.casefold() for w in _WORD.findall(a)], [w.casefold() for w in _WORD.findall(b)]
    grams = {tuple(wb[i : i + n]) for i in range(len(wb) - n + 1)}
    hit = [False] * len(wa)
    for i in range(len(wa) - n + 1):
        if tuple(wa[i : i + n]) in grams:
            for k in range(i, i + n):
                hit[k] = True
    return hit


def _shared_words(a: str, b: str) -> list[list[str]]:
    """`a` showing only the runs of 3+ words it shares with `b`; the rest become one blank per run."""
    hit = _runs(a, b)
    out: list[list[str]] = []
    for w, shared in zip(_WORD.findall(a), hit, strict=True):
        if shared and w.startswith("["):
            kind = "slot"
        elif shared:
            kind = "word"
        else:
            if not (out and out[-1][1] == "blank"):
                out.append(["", "blank"])
            continue
        if not (kind == "slot" and out and out[-1] == [w, "slot"]):
            out.append([w, kind])
    return out


def _tidy(text: str, city: str) -> str:
    """One [name] for a scrubbed business name, and [area] for any "in <Place>, <city>" (another business's
    neighbourhood is no more shown than this one's)."""
    text = " ".join(text.split())
    text = re.sub(r"\[business\](?:[\s,&]+(?:and\s+)?\[business\])*", "[name]", text, flags=re.IGNORECASE)
    if city:
        place = r"[A-Z][\w-]*(?: [A-Z][\w-]*){0,3}"  # up to four capitalised words, no overlap to backtrack over
        text = re.sub(rf"\b((?i:in|at|from)) {place} ?, ?((?i:{re.escape(city)}))\b", r"\1 [area], \2", text)
    return text


def same_script(analysis_id: str, limit: int = 2) -> list[dict[str, Any]]:
    """Checked reviewers whose review here and whose review of another business of the same kind share most of
    their wording: the same ad copy written for competitors. Shown as shared words and blanks, never whole texts."""
    from .engine.groups import type_group
    from .engine.textstyle import locality_tokens

    inp = _input(analysis_id)
    target = inp.target
    names, area = business_terms(target.title), locality_tokens(target)
    kind = type_group(target.type)[0]
    city = target.area or ""
    here = {r.contributor_id: r for r in inp.target_reviews if r.text}
    found = []
    for cid, items in inp.histories.items():
        r = here.get(cid)
        if r is None:
            continue
        for h in items:
            place = inp.places.get(h.place_key or "")
            if not h.text or place is None or h.place_key == target.place_key or type_group(place.type)[0] != kind:
                continue
            terms = names | business_terms(place.title)
            a, b = _tidy(scrub_text(r.text, terms, area), city), _tidy(scrub_text(h.text, terms, area), city)
            shared = sum(_runs(b, a))
            if shared >= 5 and shared >= 0.3 * len(_WORD.findall(b)):
                found.append((shared, {"here": _shared_words(a, b), "there": _shared_words(b, a), "type": place.type}))
    found.sort(key=lambda x: -x[0])
    return [f for _, f in found[:limit]]


_NAMEISH = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]+")


def one_voice(analysis_id: str) -> dict[str, Any] | None:
    """A checked reviewer with the most written reviews elsewhere, as a few short sentences of their own (no names,
    no numbers): what one person's voice looks like across places."""
    inp = _input(analysis_id)
    here = {r.contributor_id: r for r in inp.target_reviews if r.text}
    seen: dict[str, int] = {}  # how many reviews at the listing use each word: rare words carry a voice
    for r in inp.target_reviews:
        for w in {x.casefold() for x in _WORD.findall(r.text or "")}:
            seen[w] = seen.get(w, 0) + 1

    def rarity(text: str) -> int:
        return sum(1 for w in _WORD.findall(text) if len(w) >= 4 and seen.get(w.casefold(), 0) <= 1)

    def short(text: str, title: str | None) -> str | None:
        text = scrub_text(text, business_terms(title) | business_terms(inp.target.title), set())
        ok = [
            x.strip()
            for x in _SENTENCE.split(text)
            if 4 <= len(x.split()) <= 9
            and not re.search(r"\d|\[", x)
            and not _NAMEISH.search(x.strip())
            and not re.match(r"[A-Z][a-z]+ [a-z]+ (?:team|staff)\b", x.strip())
        ]
        return max(ok, key=lambda x: (rarity(x), -len(x)), default=None)

    best = None
    for cid, items in inp.histories.items():
        if cid not in here:
            continue
        lines = []
        mine = short(here[cid].text or "", inp.target.title)
        if mine:
            lines.append({"place": inp.target.type, "text": mine, "here": True})
        for h in items:
            place = inp.places.get(h.place_key or "")
            t = short(h.text or "", place.title if place else None) if h.place_key != inp.target.place_key else None
            if t and place:
                lines.append({"place": place.type, "text": t, "here": False})
        lines = lines[:4]
        score = sum(rarity(x["text"]) for x in lines)
        if mine and len(lines) >= 3 and (best is None or score > best[0]):
            best = (score, {"lines": lines, "reviews": len(items)})
    return best[1] if best else None


def build(hotel_id: str, mover_id: str, clean_id: str, scripted_id: str, research: str | None = None) -> dict[str, Any]:
    data = {
        "note": "Generated by reviewring.story_data from real analyses. Numbers only: no names, ids, dates or review "
        "texts, except the chatbot reply, the shared words of copied reviews (with blanks and hidden names) and a "
        "few short sentences of one reviewer (no names or numbers).",
        "hotel": hotel(_report(hotel_id)),
        "mover": mover(_report(mover_id)),
        "clean": {**clean(_report(clean_id)), "voice": one_voice(clean_id)},
        "scripted": {**scripted(_report(scripted_id)), "same_script": same_script(scripted_id, limit=1)},
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

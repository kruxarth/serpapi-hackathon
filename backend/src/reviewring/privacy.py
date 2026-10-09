"""Pseudonymization shared by presentation mode and the fixture exporter (spec 12, 14).

Businesses become "<Type> A/B/...", reviewers "Reviewer N", coordinates are
rounded to 2 decimals, and review texts are kept only when they belong to a
near-duplicate cluster written by >= 3 accounts, scrubbed and cut to 60 chars.
Chatbot or placeholder excerpts are the exception: scrubbed and cut to 180 chars. The phrases an AI model
quotes for "reads as AI-written" are kept too, scrubbed and cut to 60 chars each.
"""

from __future__ import annotations

import copy
import hashlib
import re
import secrets
import string
from collections.abc import Callable
from typing import Any

from . import config

PHONE = re.compile(r"(?:\+?\d[\d\s\-]{7,}\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
HANDLE = re.compile(r"(?<!\w)@\w+")
TEXT_KEEP_MIN_ACCOUNTS = 3
TEXT_KEEP_CHARS = 60
# Chatbot or placeholder text is kept longer: it was written by a machine, and it is the evidence. Still scrubbed.
EXCERPT_KEEP_CHARS = 180
# The short phrases an AI model quotes as the reason a review reads as AI-written. Scrubbed, cut to this length.
CUE_KEEP_CHARS = 60


def salt() -> str:
    """The pseudonym salt lives in data/ and is never committed."""
    path = config.data_dir() / "pseudonym_salt"
    if not path.exists():
        path.write_text(secrets.token_hex(16))
    return path.read_text().strip()


def hashed(value: str, kind: str, salt_value: str) -> str:
    return kind + hashlib.sha256(f"{salt_value}:{kind}:{value}".encode()).hexdigest()[:12]


def letters(i: int) -> str:
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = string.ascii_uppercase[r] + out
    return out


def business_terms(title: str | None) -> set[str]:
    """What names a business in free text: each word of its title with 3+ letters (not "and", "pvt"), and each run
    of its distinctive words as one phrase however short they are ("Om Sai" in "Om Sai Packers And Movers")."""
    from .engine.textstyle import CONNECT, GENERIC, NOT_NAME

    words = [w for w in re.split(r"\W+", title or "") if w]
    out = {w for w in words if len(w) >= 3 and w.casefold() not in NOT_NAME | CONNECT}
    run: list[str] = []
    for w in [*words, ""]:
        if w and w.casefold() not in GENERIC | NOT_NAME | CONNECT:
            run.append(w)
            continue
        if len(run) >= 2:
            out.add(" ".join(run))
        run = []
    return out


def scrub_text(text: str, business_words: set[str], area_words: set[str] | frozenset[str] = frozenset()) -> str:
    """Links, emails, phones and handles removed; the business's name becomes [business] and the listing's
    neighbourhood [area]. A multi-word term matches across any punctuation ("Om-Sai", "om sai")."""
    text = URL.sub("[link]", text)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    text = HANDLE.sub("[handle]", text)
    return scrub_names(text, business_words, area_words)


def scrub_names(text: str, business_words: set[str], area_words: set[str] | frozenset[str] = frozenset()) -> str:
    """Only the business's name and its neighbourhood: for ReviewRing's own sentences, whose dates must survive."""
    for term in sorted(business_words, key=len, reverse=True):
        parts = term.split()
        if len(parts) == 1 and len(term) < 3:
            continue
        pattern = r"\W+".join(re.escape(x) for x in parts)
        text = re.sub(rf"(?<!\w){pattern}(?!\w)", "[business]", text, flags=re.IGNORECASE)
    for word in sorted(area_words, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "[area]", text, flags=re.IGNORECASE)
    return text


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(.*)$")


def date_offset_days(salt_value: str, key: str) -> int:
    """A per-business shift of 30-365 days into the past. Intervals stay intact; the calendar doesn't."""
    digest = hashlib.sha256(f"{salt_value}:dates:{key}".encode()).digest()
    return 30 + int.from_bytes(digest[:4], "big") % 336


def shift_iso(value: str, days: int) -> str:
    from datetime import date, datetime, timedelta

    m = _ISO.match(value)
    if not m:
        return value
    if m.group(4).startswith("T"):
        try:
            return (datetime.fromisoformat(value.replace("Z", "+00:00")) - timedelta(days=days)).isoformat()
        except ValueError:
            return value
    try:
        return (date.fromisoformat(value[:10]) - timedelta(days=days)).isoformat() + value[10:]
    except ValueError:
        return value


def shift_dates(obj: Any, days: int, skip: frozenset[str] = frozenset({"analysis", "budget"})) -> Any:
    if isinstance(obj, dict):
        return {k: (v if k in skip else shift_dates(v, days, skip)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shift_dates(v, days, skip) for v in obj]
    if isinstance(obj, str):
        return shift_iso(obj, days)
    return obj


_EMBEDDED_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _scrub_sentences(
    r: dict[str, Any], original: dict[str, Any], days: int, names: Callable[[str], str] = lambda t: t
) -> dict[str, Any]:
    """Evidence and reasons are prose: hide the names in them, shift their dates and blur exact review counts."""
    total = original.get("place", {}).get("total_reviews")
    gap = original.get("signals", {}).get("T7") or {}
    swaps: list[tuple[str, str]] = []
    if total:
        swaps.append((f"{total:,}", f"about {approx_count(total):,}"))
        swaps.append((str(total), f"about {approx_count(total)}"))
    if gap.get("older_count"):
        n = gap["older_count"]
        swaps.append((f"{n:,}", f"about {approx_count(n):,}"))

    def fix(text: str) -> str:
        text = names(text)
        for a, b in swaps:
            text = text.replace(a, b)
        return _EMBEDDED_DATE.sub(lambda m: shift_iso(m.group(0), days), text)

    for e in r.get("evidence", []):
        e["text"] = fix(e["text"])
    if r.get("level"):
        r["level"]["reasons"] = [fix(x) for x in r["level"]["reasons"]]
    if r.get("ai_summary"):
        r["ai_summary"]["paragraphs"] = [fix(x) for x in r["ai_summary"].get("paragraphs", [])]
        r["ai_summary"].pop("facts", None)
    return r


def approx_count(n: int | None) -> int | None:
    """One significant figure (640 -> 600, 2300 -> 2000): the review count alone shouldn't identify a business."""
    if not n:
        return n
    magnitude = 10 ** (len(str(int(n))) - 1)
    return max(1, round(n / magnitude)) * magnitude


def round1(v: float | None) -> float | None:
    """One decimal (about 11 km): two decimals can single out a small business."""
    return None if v is None else round(float(v), 1)


class Pseudonymizer:
    def __init__(self, report: dict[str, Any], salt_value: str | None = None) -> None:
        self.salt = salt_value if salt_value is not None else salt()
        self.places: dict[str, str] = {}
        self.place_ids: dict[str, str] = {}
        self.reviewers: dict[str, str] = {}
        self.reviewer_ids: dict[str, str] = {}
        self.review_ids: dict[str, str] = {}
        self.clusters: dict[str, str] = {}
        self._report = report
        self._index()

    def _index(self) -> None:
        r = self._report
        place_keys = [r["place"]["place_key"]]
        for rows in r.get("client_lists", {}).values():
            place_keys += [row["place_key"] for row in rows]
        place_keys += sorted(r.get("places", {}))
        for e in r.get("graph", {}).get("edges", []):
            place_keys += [s["place_key"] for s in e["shared"]]
        types: dict[str, str | None] = {r["place"]["place_key"]: r["place"].get("type")}
        for k, p in r.get("places", {}).items():
            types.setdefault(k, p.get("type"))
        for rows in r.get("client_lists", {}).values():
            for row in rows:
                types.setdefault(row["place_key"], row.get("type"))
        for key in place_keys:
            if key in self.places:
                continue
            letter = letters(len(self.places))
            t = types.get(key)
            self.places[key] = f"{t} {letter}" if t else f"Business {letter}"
            self.place_ids[key] = hashed(key, "p", self.salt)
        order = [x["contributor_id"] for x in r.get("reviewers", [])]
        order += [x["contributor_id"] for x in r.get("reviews", []) if x.get("contributor_id")]
        for cid in order:
            if cid and cid not in self.reviewers:
                self.reviewers[cid] = f"Reviewer {len(self.reviewers) + 1}"
                self.reviewer_ids[cid] = hashed(cid, "u", self.salt)
        clusters = sorted({x["cluster"] for x in r.get("reviews", []) if x.get("cluster")})
        for c in r.get("signals", {}).get("T4", {}).get("stock_phrase_clusters", []):
            clusters.append(c)
        for i, c in enumerate(sorted(set(clusters))):
            self.clusters[c] = f"c{i + 1}"

    def place(self, key: str | None) -> str | None:
        return None if key is None else self.place_ids.get(key, hashed(key, "p", self.salt))

    def person(self, cid: str | None) -> str | None:
        return None if cid is None else self.reviewer_ids.get(cid, hashed(cid, "u", self.salt))

    def review(self, rid: str) -> str:
        return self.review_ids.setdefault(rid, hashed(rid, "r", self.salt))

    def cluster(self, c: str | None) -> str | None:
        return None if c is None else self.clusters.get(c, hashed(c, "c", self.salt))


def _round(v: float | None) -> float | None:
    return round1(v)


def keep_text(row: dict[str, Any], cluster_accounts: dict[str, int]) -> bool:
    c = row.get("cluster")
    return bool(c and cluster_accounts.get(c, 0) >= TEXT_KEEP_MIN_ACCOUNTS and row.get("text"))


def pseudonymize_report(report: dict[str, Any], salt_value: str | None = None) -> dict[str, Any]:
    """A copy of the report safe to show in a demo or commit as a fixture."""
    ps = Pseudonymizer(report, salt_value)
    r = copy.deepcopy(report)
    business_words = business_terms(report["place"].get("title"))
    area_words = set(r["place"].pop("locality", None) or [])  # the neighbourhood: scrubbed, never shown

    def scrub(text: str) -> str:
        return scrub_text(text, business_words, area_words)

    tk = report["place"]["place_key"]
    r["place"].update(
        place_key=ps.place(tk),
        title=ps.places.get(tk),
        lat=_round(r["place"].get("lat")),
        lng=_round(r["place"].get("lng")),
    )
    r["places"] = {
        ps.place(k): {**v, "title": ps.places.get(k), "lat": _round(v.get("lat")), "lng": _round(v.get("lng"))}
        for k, v in report.get("places", {}).items()
    }
    for gid, rows in r.get("client_lists", {}).items():
        for row in rows:
            row["title"] = ps.places.get(row["place_key"])
            row["place_key"] = ps.place(row["place_key"])
            row["members"] = [ps.person(m) for m in row["members"]]
            row["lat"], row["lng"] = _round(row.get("lat")), _round(row.get("lng"))
        r["client_lists"][gid] = rows
    for g in r.get("groups", []):
        g["members"] = [ps.person(m) for m in g["members"]]
        g["pruned"] = [ps.person(m) for m in g["pruned"]]
        g["edges"] = [[ps.person(u), ps.person(v)] for u, v in g["edges"]]
        g["core_places"] = [ps.place(k) for k in g["core_places"]]
    for rev in r.get("reviewers", []):
        cid = rev["contributor_id"]
        rev["contributor_id"] = ps.person(cid)
        rev["display_name"] = ps.reviewers.get(cid)
        for b in rev.get("badges", []):
            if isinstance(b.get("places"), list):  # place keys (A9 keeps a count under the same name)
                b["places"] = [ps.place(k) for k in b["places"]]
            for occ in b.get("occasions", []):
                occ["places"] = [ps.place(k) for k in occ["places"]]
            if "cluster" in b:
                b["cluster"] = ps.cluster(b["cluster"])
    r["histories"] = {
        ps.person(cid): {
            **h,
            "items": [
                {
                    **it,
                    "place_key": ps.place(it["place_key"]),
                    "lat": _round(it.get("lat")),
                    "lng": _round(it.get("lng")),
                }
                for it in h.get("items", [])
            ],
        }
        for cid, h in report.get("histories", {}).items()
    }
    graph = r.get("graph", {})
    for n in graph.get("nodes", []):
        n["display_name"] = ps.reviewers.get(n["id"])
        n["id"] = ps.person(n["id"])
    for e in graph.get("edges", []):
        e["source"], e["target"] = ps.person(e["source"]), ps.person(e["target"])
        for s in e["shared"]:
            s["place_key"] = ps.place(s["place_key"])

    accounts: dict[str, set[str]] = {}
    for row in report.get("reviews", []):
        if row.get("cluster"):
            accounts.setdefault(row["cluster"], set()).add(row.get("contributor_id") or row["review_id"])
    counts = {c: len(a) for c, a in accounts.items()}
    for row, orig in zip(r.get("reviews", []), report.get("reviews", []), strict=True):
        text = orig.get("text") or ""
        if keep_text(orig, counts):
            row["text"] = scrub(text)[:TEXT_KEEP_CHARS]
            row["text_included"] = True
        else:
            row["text"] = None
            row["text_included"] = False
        row["text_length"] = orig.get("text_length")
        row["review_id"] = ps.review(orig["review_id"])
        row["display_name"] = ps.reviewers.get(orig.get("contributor_id") or "")
        row["contributor_id"] = ps.person(orig.get("contributor_id"))
        row["cluster"] = ps.cluster(orig.get("cluster"))
        row["copied_with"] = [ps.review(x) for x in orig.get("copied_with") or []]
        if orig.get("excerpt"):
            row["excerpt"] = scrub(orig["excerpt"])[:EXCERPT_KEEP_CHARS]
        if orig.get("voice"):
            row["voice"] = {
                **orig["voice"],
                "here": scrub(orig["voice"].get("here", ""))[:CUE_KEEP_CHARS],
                "elsewhere": scrub(orig["voice"].get("elsewhere", ""))[:CUE_KEEP_CHARS],
                "others": [],  # the reviewer's own words elsewhere stay private in a recording
            }
        if orig.get("keyword_phrase"):
            row["keyword_phrase"] = scrub(orig["keyword_phrase"])
        if orig.get("ai"):
            row["ai"] = {
                **orig["ai"],
                "cues": [scrub(c)[:CUE_KEEP_CHARS] for c in orig["ai"].get("cues", [])],
            }
    t4 = r.get("signals", {}).get("T4", {})
    if t4:
        t4["clusters"] = {ps.cluster(c): [ps.review(x) for x in ids] for c, ids in t4.get("clusters", {}).items()}
        t4["stock_phrase_clusters"] = [ps.cluster(c) for c in t4.get("stock_phrase_clusters", [])]
    for c in r.get("signals", {}).get("T11", {}).get("clusters", []):
        c["review_ids"] = [ps.review(x) for x in c.get("review_ids", [])]  # its times are shifted with every date
    t8 = r.get("signals", {}).get("T8", {})
    for hit in t8.get("generated", []) if t8.get("available") else []:
        hit["review_id"] = ps.review(hit["review_id"])
        if hit.get("excerpt"):
            hit["excerpt"] = scrub(hit["excerpt"])[:EXCERPT_KEEP_CHARS]
    t10 = r.get("signals", {}).get("T10")
    if t10:
        t10["review_ids"] = [ps.review(x) for x in t10.get("review_ids", [])]
        t10["named_ids"] = [ps.review(x) for x in t10.get("named_ids", [])]
        t10["phrases"] = {scrub(k): v for k, v in t10.get("phrases", {}).items()}
    t1 = r.get("signals", {}).get("T1", {})
    for b in t1.get("bursts", []):
        b["review_ids"] = [ps.review(x) for x in b.get("review_ids", [])]
    r["sample"]["baseline"] = [ps.person(x) for x in r["sample"].get("baseline", [])]
    r.pop("names", None)
    r["place"]["total_reviews"] = approx_count(r["place"].get("total_reviews"))
    if r.get("ratings", {}).get("overall"):
        r["ratings"]["overall"]["total_as_displayed"] = approx_count(r["ratings"]["overall"]["total_as_displayed"])
    for row in r.get("reviews", []):
        row.pop("date", None)  # exact timestamps; the shifted day is enough
    days = date_offset_days(ps.salt, tk)
    r = shift_dates(r, days)
    r = _scrub_sentences(r, report, days, lambda t: scrub_names(t, business_words, area_words))
    r["pseudonymized"] = True
    r["dates_shifted"] = True
    return r

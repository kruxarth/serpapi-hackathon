"""Pseudonymization shared by presentation mode and the fixture exporter (spec 12, 14).

Businesses become "<Type> A/B/...", reviewers "Reviewer N", coordinates are
rounded to 2 decimals, and review texts are kept only when they belong to a
near-duplicate cluster written by >= 3 accounts, scrubbed and cut to 60 chars.
"""

from __future__ import annotations

import copy
import hashlib
import re
import secrets
import string
from typing import Any

from . import config

PHONE = re.compile(r"(?:\+?\d[\d\s\-]{7,}\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
HANDLE = re.compile(r"(?<!\w)@\w+")
TEXT_KEEP_MIN_ACCOUNTS = 3
TEXT_KEEP_CHARS = 60


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


def scrub_text(text: str, business_words: set[str]) -> str:
    text = URL.sub("[link]", text)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    text = HANDLE.sub("[handle]", text)
    for word in sorted(business_words, key=len, reverse=True):
        if len(word) >= 3:
            text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "[business]", text, flags=re.IGNORECASE)
    return text


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
    return None if v is None else round(float(v), 2)


def keep_text(row: dict[str, Any], cluster_accounts: dict[str, int]) -> bool:
    c = row.get("cluster")
    return bool(c and cluster_accounts.get(c, 0) >= TEXT_KEEP_MIN_ACCOUNTS and row.get("text"))


def pseudonymize_report(report: dict[str, Any], salt_value: str | None = None) -> dict[str, Any]:
    """A copy of the report safe to show in a demo or commit as a fixture."""
    ps = Pseudonymizer(report, salt_value)
    r = copy.deepcopy(report)
    title = report["place"].get("title") or ""
    business_words = {w for w in re.split(r"\W+", title) if len(w) >= 4}

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
            if "places" in b:
                b["places"] = [ps.place(k) for k in b["places"]]
            for occ in b.get("occasions", []):
                occ["places"] = [ps.place(k) for k in occ["places"]]
            if "cluster" in b:
                b["cluster"] = ps.cluster(b["cluster"])
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
            row["text"] = scrub_text(text, business_words)[:TEXT_KEEP_CHARS]
            row["text_included"] = True
        else:
            row["text"] = None
            row["text_included"] = False
        row["text_length"] = orig.get("text_length")
        row["review_id"] = ps.review(orig["review_id"])
        row["display_name"] = ps.reviewers.get(orig.get("contributor_id") or "")
        row["contributor_id"] = ps.person(orig.get("contributor_id"))
        row["cluster"] = ps.cluster(orig.get("cluster"))
    t4 = r.get("signals", {}).get("T4", {})
    if t4:
        t4["clusters"] = {ps.cluster(c): [ps.review(x) for x in ids] for c, ids in t4.get("clusters", {}).items()}
        t4["stock_phrase_clusters"] = [ps.cluster(c) for c in t4.get("stock_phrase_clusters", [])]
    t1 = r.get("signals", {}).get("T1", {})
    for b in t1.get("bursts", []):
        b["review_ids"] = [ps.review(x) for x in b.get("review_ids", [])]
    r["sample"]["baseline"] = [ps.person(x) for x in r["sample"].get("baseline", [])]
    r.pop("names", None)
    r["pseudonymized"] = True
    return r

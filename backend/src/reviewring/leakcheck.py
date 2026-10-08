"""Leak check for committed fixtures (spec section 14).

Fails on URLs, phone numbers, emails, 6-digit PIN codes in text, and on any
original identifier found in the local cache: contributor ids, reviewer names,
business titles and review ids. Run by the exporter and the pre-commit hook:

    uv run --project backend python -m reviewring.leakcheck fixtures
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, db

URL = re.compile(
    r"https?://|www\.|googleusercontent\.com|google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/", re.IGNORECASE
)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)|\+\d{1,3}[\s\-]?\d[\d\s\-]{7,}\d")
PIN = re.compile(r"(?<![\d\-])[1-9]\d{2}\s?\d{3}(?![\d\-])")
# Keys whose values are hashes or opaque ids made by the exporter, not free text.
HASH_KEY = re.compile(r"(hash|_key|salted|^id$|_id$)", re.IGNORECASE)
# Values shaped exactly like the exporter's salted ids ("u3fa9...", "t:r12ab...", "h:u..:r.."), never free text.
ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+\-]\d{2}:?\d{2})?)?$")
HASHED_ID = re.compile(r"^(?:[th]:)?[a-z][0-9a-f]{12}(?::[a-z][0-9a-f]{12})?$")


@dataclass
class Finding:
    file: str
    where: str
    kind: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.file}: {self.where}: {self.kind}: {self.excerpt}"


def _mask(text: str, match: re.Match[str] | None = None) -> str:
    if match is None:
        return "***"
    start = max(0, match.start() - 12)
    return (text[start : match.start()] + "***" + text[match.end() : match.end() + 12]).replace("\n", " ")


def _walk(obj: Any, path: str = "$", key: str = "") -> Iterator[tuple[str, str, str, bool]]:
    """Yield (json path, key, value as text, is a string) for every scalar, and for dict keys."""
    if isinstance(obj, dict):
        for k, value in obj.items():
            yield f"{path}.{k}[key]", "", str(k), True
            yield from _walk(value, f"{path}.{k}", str(k))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk(value, f"{path}[{i}]", key)
    elif isinstance(obj, str):
        yield path, key, obj, True
    elif obj is not None and not isinstance(obj, bool):
        yield path, key, str(obj), False


def originals_from_cache(db_path: Path | None = None) -> dict[str, set[str]]:
    """Identifiers that must never appear in a fixture, taken from raw cached responses."""
    out: dict[str, set[str]] = {
        "contributor id": set(),
        "reviewer name": set(),
        "business title": set(),
        "review id": set(),
    }
    path = db_path or db.default_path()
    if not Path(path).exists():
        return out
    conn = db.connect(path)
    for (body,) in conn.execute("SELECT body FROM raw_responses WHERE status = 'ok'"):
        try:
            data = json.loads(body)
        except ValueError:
            continue
        _collect(data, out)
    return out


def _collect(data: dict[str, Any], out: dict[str, set[str]]) -> None:
    for place in [data.get("place_info"), data.get("place_results"), *(data.get("local_results") or [])]:
        if isinstance(place, dict) and place.get("title"):
            out["business title"].add(str(place["title"]))
    contributor = data.get("contributor") or {}
    if contributor.get("name"):
        out["reviewer name"].add(str(contributor["name"]))
    for review in data.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        if review.get("review_id"):
            out["review id"].add(str(review["review_id"]))
        user = review.get("user") or {}
        if user.get("name"):
            out["reviewer name"].add(str(user["name"]))
        if user.get("contributor_id"):
            out["contributor id"].add(str(user["contributor_id"]))
        place = review.get("place_info") or {}
        if place.get("title"):
            out["business title"].add(str(place["title"]))
    params = data.get("search_parameters") or {}
    if params.get("contributor_id"):
        out["contributor id"].add(str(params["contributor_id"]))


# Words that say what or where a business is, not which one. A business title made only of these ("New Delhi",
# "Best Packers And Movers") names nothing a fixture could leak, and matching it would flag every review that uses
# the phrase.
GENERIC_TITLE_WORDS = {
    "best",
    "top",
    "good",
    "the",
    "and",
    "&",
    "new",
    "old",
    "packers",
    "movers",
    "packaging",
    "transport",
    "logistics",
    "relocation",
    "services",
    "service",
    "hotel",
    "hotels",
    "clinic",
    "care",
    "skin",
    "dental",
    "hospital",
    "restaurant",
    "cafe",
    "store",
    "shop",
    "india",
    "co",
    "company",
    "pvt",
    "ltd",
}


def _generic_title(value: str) -> bool:
    from .normalize.geo import known_area_names

    places = {w.casefold() for name in known_area_names() for w in name.split()}
    words = [w.casefold() for w in re.findall(r"[\w&]+", value)]
    return len(value) < 6 or all(w in GENERIC_TITLE_WORDS or w in places for w in words)


def _original_patterns(originals: dict[str, set[str]]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for kind, values in originals.items():
        for value in values:
            value = value.strip()
            if len(value) < 4:
                continue  # too short to match without false positives
            if kind == "business title" and _generic_title(value):
                continue
            patterns.append((kind, re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.IGNORECASE)))
    return patterns


def check_object(obj: Any, name: str, originals: dict[str, set[str]] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    patterns = _original_patterns(originals or {})
    for where, key, text, is_text in _walk(obj):
        for kind, regex in (("URL", URL), ("email address", EMAIL)):
            if m := regex.search(text):
                findings.append(Finding(name, where, kind, _mask(text, m)))
        free_text = is_text and not HASH_KEY.search(key) and not HASHED_ID.match(text) and not ISO_TIME.match(text)
        if free_text:
            if m := PHONE.search(text):
                findings.append(Finding(name, where, "phone number", _mask(text, m)))
            if m := PIN.search(text):
                findings.append(Finding(name, where, "PIN code", _mask(text, m)))
        for kind, regex in patterns:
            if m := regex.search(text):
                findings.append(Finding(name, where, f"original {kind}", _mask(text, m)))
    return findings


def check_paths(paths: list[Path], originals: dict[str, set[str]] | None = None) -> list[Finding]:
    if originals is None:
        originals = originals_from_cache()
    findings: list[Finding] = []
    for root in paths:
        files = sorted(root.rglob("*.json")) if root.is_dir() else [root]
        for file in files:
            try:
                obj = json.loads(file.read_text(encoding="utf-8"))
            except ValueError as exc:
                findings.append(Finding(str(file), "$", "unreadable JSON", str(exc)))
                continue
            findings.extend(check_object(obj, str(file), originals))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    paths = [Path(a) for a in args] or [config.REPO_ROOT / "fixtures"]
    findings = check_paths([p for p in paths if p.exists()])
    for f in findings:
        print(f"LEAK {f}", file=sys.stderr)
    if findings:
        print(f"Leak check failed: {len(findings)} finding(s).", file=sys.stderr)
        return 1
    print("Leak check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

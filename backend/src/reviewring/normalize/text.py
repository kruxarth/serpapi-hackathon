"""Review text: extraction, normalization, 3-gram similarity and near-duplicate clusters (spec 9.1)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .. import config

_TRANSLATED = re.compile(r"\(Translated by Google\)\s*", re.IGNORECASE)
_ORIGINAL = re.compile(r"\s*\(Original\)\s*", re.IGNORECASE)


def review_text(review: dict[str, Any]) -> str:
    """The original-language text: ``extracted_snippet.original``, else ``snippet`` without Google's markers."""
    extracted = review.get("extracted_snippet")
    if isinstance(extracted, dict) and extracted.get("original") is not None:
        return str(extracted["original"]).strip()
    snippet = review.get("snippet")
    if not snippet:
        return ""
    snippet = str(snippet)
    if _ORIGINAL.search(snippet):
        # "(Translated by Google) <translation> (Original) <original>": keep the original.
        return _ORIGINAL.split(snippet, maxsplit=1)[1].strip()
    return _TRANSLATED.sub("", snippet).strip()


def normalize(text: str) -> str:
    """NFKC, lower-case, keep letters, combining marks and numbers (L*, M*, N*) plus spaces."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    kept = [ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in text]
    return " ".join("".join(kept).split())


def script_of(text: str) -> str:
    """latin | devanagari | indic | other | mixed | none, from the Unicode script of the letters."""
    scripts: set[str] = set()
    for ch in text or "":
        if unicodedata.category(ch)[0] != "L":
            continue
        cp = ord(ch)
        if cp < 0x0250 or 0x1E00 <= cp <= 0x1EFF:
            scripts.add("latin")
        elif 0x0900 <= cp <= 0x097F:
            scripts.add("devanagari")
        elif 0x0980 <= cp <= 0x0DFF:
            scripts.add("indic")
        else:
            scripts.add("other")
    if not scripts:
        return "none"
    return scripts.pop() if len(scripts) == 1 else "mixed"


def ngrams(normalized: str, n: int | None = None) -> frozenset[str]:
    n = n or int(config.tunable("text", "ngram"))
    if len(normalized) < n:
        return frozenset([normalized]) if normalized else frozenset()
    return frozenset(normalized[i : i + n] for i in range(len(normalized) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def is_short(normalized: str) -> bool:
    return len(normalized) <= int(config.tunable("text", "short_max_chars"))


@dataclass
class TextItem:
    """One review text inside an analysis. ``owner`` is the contributor (None for anonymous)."""

    text_id: str
    owner: str | None
    text: str
    is_target: bool  # a review of the target business


@dataclass
class TextFeatures:
    text_id: str
    owner: str | None
    length: int  # normalized characters
    script: str
    short: bool
    cluster: str | None  # near-duplicate cluster id, stable for the same inputs
    target_cluster: str | None = None  # cluster among target reviews only (used by the priority score)


def near_duplicate_clusters(items: list[TextItem]) -> dict[str, TextFeatures]:
    """Near-duplicate clusters anchored on target reviews.

    Pairs are (target review, any text) with Jaccard >= threshold, both >= min chars
    and different owners. Clusters are connected components; ids are "c" + the
    smallest member text_id, so they're stable.
    """
    threshold = float(config.tunable("text", "near_duplicate_similarity"))
    min_chars = int(config.tunable("text", "near_duplicate_min_chars"))
    norm = {it.text_id: normalize(it.text) for it in items}
    grams = {tid: ngrams(t) for tid, t in norm.items() if len(t) >= min_chars}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            parent[hi] = lo

    eligible = sorted((it for it in items if it.text_id in grams), key=lambda it: it.text_id)
    targets = [it for it in eligible if it.is_target]
    sizes = {tid: len(g) for tid, g in grams.items()}
    for t in targets:
        gt = grams[t.text_id]
        st = sizes[t.text_id]
        for other in eligible:
            if other.text_id == t.text_id:
                continue
            if other.owner is not None and other.owner == t.owner:
                continue
            so = sizes[other.text_id]
            if min(st, so) < threshold * max(st, so):  # Jaccard can't reach the threshold
                continue
            if jaccard(gt, grams[other.text_id]) >= threshold:
                union(t.text_id, other.text_id)

    members: dict[str, list[str]] = {}
    for tid in grams:
        members.setdefault(find(tid), []).append(tid)
    cluster_of: dict[str, str] = {}
    for group in members.values():
        if len(group) >= 2:
            cid = "c" + min(group)
            for tid in group:
                cluster_of[tid] = cid

    out = {}
    for it in items:
        n = norm[it.text_id]
        out[it.text_id] = TextFeatures(
            text_id=it.text_id,
            owner=it.owner,
            length=len(n),
            script=script_of(it.text),
            short=is_short(n),
            cluster=cluster_of.get(it.text_id),
        )
    return out


def cluster_owners(features: Iterable[TextFeatures]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in features:
        if f.cluster:
            out.setdefault(f.cluster, set()).add(f.owner or f"anon:{f.text_id}")
    return out

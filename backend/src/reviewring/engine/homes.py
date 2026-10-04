"""Home areas: where a reviewer's own life happens.

A reviewer's home is the most common area among their *personal* places: places
no other checked reviewer reviewed. Real social groups share a home and their
shared places sit near it; review farms share clients, and their members' homes
differ or can't be determined (their history is mostly clients).

Used two ways: a shared place near either reviewer's home isn't surprising
(friends from Pune sharing Pune cafes, even when the business is in Goa), and a
group whose members mostly share a home near most of its core places is a
neutral "social circle", not a ring.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .. import config
from ..model import AnalysisInput


@dataclass(frozen=True)
class Home:
    area: str
    lat: float
    lng: float
    places: int  # personal places in the home area


def compute_homes(inp: AnalysisInput, contributors: list[str]) -> dict[str, Home]:
    cfg = config.load_tunables()["homes"]
    reviewed_by: dict[str, set[str]] = {}
    for cid in contributors:
        for h in inp.histories.get(cid, []):
            if h.place_key and h.place_key != inp.target.place_key:
                reviewed_by.setdefault(h.place_key, set()).add(cid)
    homes: dict[str, Home] = {}
    for cid in sorted(set(contributors)):
        personal = []
        seen: set[str] = set()
        for h in inp.histories.get(cid, []):
            key = h.place_key
            if not key or key == inp.target.place_key or key in seen or reviewed_by.get(key, set()) - {cid}:
                continue
            seen.add(key)
            p = inp.places.get(key)
            if p is not None and p.area and p.lat is not None and p.lng is not None:
                personal.append(p)
        if len(personal) < cfg["min_personal_places"]:
            continue
        counts = Counter(p.area for p in personal)
        area, n = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if n < cfg["min_mode_count"] or n / len(personal) < cfg["min_mode_share"]:
            continue
        here = [p for p in personal if p.area == area]
        homes[cid] = Home(area, sum(p.lat for p in here) / len(here), sum(p.lng for p in here) / len(here), n)  # type: ignore[misc]
    return homes

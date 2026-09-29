"""Areas (for "how many cities" counts and wording) and distances (spec 9.1).

The "far" test always uses distance; areas are only for counting and naming.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from .. import config

_PIN = re.compile(r"\b\d{3}\s?\d{3}\b")
_POSTAL = re.compile(r"\b[A-Z0-9]{2,5}(?:[\s\-][A-Z0-9]{2,4})?\b")
_EARTH_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s&\-]", " ", text.casefold()).replace("-", " ").split())


@lru_cache(maxsize=1)
def _tables() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    geo = config.load_tunables()["geo"]
    states = {_key(s): s for s in [*geo["states"], *geo["union_territories"]]}
    for alias, canonical in geo["state_aliases"].items():
        states[_key(alias)] = canonical
    metros: dict[str, str] = {}
    for canonical, *members in geo["metros"]:
        for m in members:
            metros[_key(m)] = canonical
    countries = {_key(k): v for k, v in geo["country_short"].items()}
    return states, metros, countries


def clear_cache() -> None:
    _tables.cache_clear()


def known_area_names() -> set[str]:
    """States, UTs and metro members: used by the LLM validator to catch stray place names."""
    states, metros, _ = _tables()
    geo = config.load_tunables()["geo"]
    names = {*geo["states"], *geo["union_territories"], *geo["state_aliases"]}
    for canonical, *members in geo["metros"]:
        names.add(canonical)
        names.update(members)
    return names


def _clean_component(part: str) -> str:
    part = _PIN.sub("", part)
    return " ".join(part.split()).strip(" -")


def city_alias(city: str) -> str:
    _, metros, _ = _tables()
    return metros.get(_key(city), city)


def area_from_address(address: str | None) -> str | None:
    """Indian addresses: the component before the state (metro aliases merged).
    Other countries: "City, Country". None when it can't be parsed."""
    if not address:
        return None
    states, _, countries = _tables()
    parts = [_clean_component(p) for p in address.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    if _key(parts[-1]) == "india":
        parts = parts[:-1]
        if not parts:
            return None
        india = True
    else:
        india = False

    state_index = None
    for i in range(len(parts) - 1, -1, -1):
        if _key(parts[i]) in states:
            state_index = i
            break
    if state_index is not None:
        state = states[_key(parts[state_index])]
        city = parts[state_index - 1] if state_index > 0 else state
        city = re.sub(r"\d+", "", city).strip() or state
        return city_alias(city)
    if india:
        # No state found, but the address is Indian: take the last component as the city.
        return city_alias(re.sub(r"\d+", "", parts[-1]).strip()) or None
    if len(parts) >= 2:
        country = countries.get(_key(parts[-1]), parts[-1])
        city = _POSTAL.sub("", parts[-2]).strip() or parts[-2]
        city = re.sub(r"\d+", "", city).strip() or parts[-2]
        return f"{city}, {country}"
    return None


@dataclass
class AreaPoint:
    key: str
    area: str | None
    lat: float | None
    lng: float | None


def assign_areas(points: Iterable[AreaPoint], radius_km: float | None = None) -> dict[str, str | None]:
    """Fill in areas for places whose address couldn't be parsed, by greedy coordinate clustering.

    Places are processed in key order so the result doesn't depend on fetch order.
    Each cluster is named after the nearest named place's area, or "Unnamed area N".
    """
    radius = radius_km if radius_km is not None else float(config.tunable("areas", "cluster_radius_km"))
    points = sorted(points, key=lambda p: p.key)
    out: dict[str, str | None] = {p.key: p.area for p in points}
    named = [p for p in points if p.area and p.lat is not None and p.lng is not None]
    todo = [p for p in points if not p.area and p.lat is not None and p.lng is not None]
    clusters: list[tuple[AreaPoint, list[AreaPoint]]] = []
    for p in todo:
        for seed, members in clusters:
            if haversine_km(seed.lat, seed.lng, p.lat, p.lng) <= radius:  # type: ignore[arg-type]
                members.append(p)
                break
        else:
            clusters.append((p, [p]))
    unnamed = 0
    for seed, members in clusters:
        best = None
        for n in named:
            d = haversine_km(seed.lat, seed.lng, n.lat, n.lng)  # type: ignore[arg-type]
            if d <= radius and (best is None or (d, n.key) < best[:2]):
                best = (d, n.key, n.area)
        if best:
            name = best[2]
        else:
            unnamed += 1
            name = f"Unnamed area {unnamed}"
        for m in members:
            out[m.key] = name
    return out

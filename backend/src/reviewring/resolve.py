"""Turn user input into a place (spec section 8).

Order of preference: a URL with a data_id (free), a short link (free to
expand, no SerpApi), a CID URL (1 search), a place_id-only URL (1 search),
then name + city text (1 search, the user picks a candidate).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import requests

from . import config
from .serp import catalog
from .serp.gateway import Gateway

DATA_ID = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+", re.IGNORECASE)
PLACE_COORDS = re.compile(r"!8m2!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
PLACE_ID_TOKEN = re.compile(r"!1s(ChIJ[A-Za-z0-9_\-]+)")
PLACE_ID_Q = re.compile(r"place_id:(ChIJ[A-Za-z0-9_\-]+)")
GOOGLE_HOST = re.compile(r"^(?:www\.)?google\.[a-z]{2,3}(?:\.[a-z]{2})?$")
MAPS_HOST = re.compile(r"^maps\.google\.[a-z]{2,3}(?:\.[a-z]{2})?$")
SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl"}


class InputRefused(ValueError):
    """The input can't be analysed. The message is shown to the user."""


@dataclass
class ResolvedInput:
    kind: str  # data_id | cid | place_id | name
    cost: int  # searches needed to identify the place
    url: str | None = None
    data_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    cid: str | None = None
    place_id: str | None = None
    query: str | None = None
    expanded_from: str | None = None  # the short link, when one was followed


@dataclass
class PlaceCandidate:
    data_id: str | None
    place_id: str | None
    title: str | None
    address: str | None
    type: str | None
    rating: float | None
    reviews: int | None
    lat: float | None
    lng: float | None
    extra: dict[str, Any] = field(default_factory=dict)


def _full_unquote(text: str) -> str:
    for _ in range(3):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _looks_like_url(text: str) -> bool:
    if re.match(r"^[a-z][a-z0-9+.\-]*://", text, re.IGNORECASE):
        return True
    host = text.split("/", 1)[0].lower()
    return bool(GOOGLE_HOST.match(host) or MAPS_HOST.match(host) or host in SHORT_HOSTS)


def _split(url: str):
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.IGNORECASE):
        url = "https://" + url
    return url, urlsplit(url)


def _is_short(parts) -> bool:
    host = (parts.hostname or "").lower()
    return host == "maps.app.goo.gl" or (host == "goo.gl" and parts.path.startswith("/maps"))


def _is_maps(parts) -> bool:
    host = (parts.hostname or "").lower()
    if MAPS_HOST.match(host):
        return True
    return bool(GOOGLE_HOST.match(host)) and (parts.path == "/maps" or parts.path.startswith("/maps/"))


def parse_maps_url(url: str) -> ResolvedInput:
    """Parse a full Google Maps URL. No network."""
    url, parts = _split(url.strip())
    if not _is_maps(parts):
        raise InputRefused("That isn't a Google Maps link. Paste a place link from Google Maps, or a name and city.")
    if "/maps/dir/" in parts.path or parts.path.rstrip("/") == "/maps/dir":
        raise InputRefused("That's a directions link. Open the place itself on Google Maps and copy its link.")

    decoded = _full_unquote(url)
    ids = [m.group(0).lower() for m in DATA_ID.finditer(decoded)]
    distinct = list(dict.fromkeys(ids))
    if len(distinct) >= 2:
        raise InputRefused("That link lists several places. Open one place and copy its link.")
    if distinct:
        data_id = distinct[0]
        lat = lng = None
        start = decoded.lower().find(data_id)
        match = PLACE_COORDS.search(decoded, max(start, 0)) or PLACE_COORDS.search(decoded)
        if match:
            lat, lng = float(match.group(1)), float(match.group(2))
        return ResolvedInput(kind="data_id", cost=0, url=url, data_id=data_id, lat=lat, lng=lng)

    query = parse_qs(parts.query)
    cid = (query.get("cid") or [None])[0]
    if cid and cid.isdigit():
        return ResolvedInput(kind="cid", cost=1, url=url, cid=cid)

    place_id = (query.get("place_id") or query.get("query_place_id") or [None])[0]
    if not place_id:
        match = PLACE_ID_TOKEN.search(decoded) or PLACE_ID_Q.search(decoded)
        place_id = match.group(1) if match else None
    if place_id:
        return ResolvedInput(kind="place_id", cost=1, url=url, place_id=place_id)

    raise InputRefused("Couldn't find a place in that link. Open the place on Google Maps and copy its link.")


def expand_short_link(url: str, session: requests.Session | None = None) -> str:
    """Follow a maps.app.goo.gl / goo.gl/maps redirect chain with plain HTTP (not SerpApi)."""
    session = session or requests.Session()
    timeout = config.tunable("resolve", "short_link_timeout_seconds")
    max_redirects = config.tunable("resolve", "short_link_max_redirects")
    headers = {"User-Agent": config.tunable("resolve", "user_agent")}
    seen: set[str] = set()
    current = url
    for _ in range(max_redirects + 1):
        if current in seen:
            raise InputRefused("That short link redirects in a loop.")
        seen.add(current)
        parts = urlsplit(current)
        if (parts.hostname or "").lower().startswith("consent.google."):
            target = (parse_qs(parts.query).get("continue") or [None])[0]
            if not target:
                raise InputRefused("The short link led to a Google consent page without a destination.")
            current = target
            continue
        if not _is_short(parts):
            return current
        try:
            resp = session.get(current, headers=headers, timeout=timeout, allow_redirects=False)
        except requests.RequestException:
            # Some ISPs' DNS (seen with Jio) answer goo.gl with addresses that never respond. Resolve it through
            # DNS-over-HTTPS and connect to Google's own address; TLS is still verified against the hostname.
            resp = _fetch_via_doh(current, headers, timeout)
            if resp is None:
                raise InputRefused(
                    "Couldn't open that short link: your network may be blocking goo.gl links. Open it in your "
                    "browser and paste the full google.com/maps link instead."
                ) from None
        location = resp.headers.get("Location")
        if resp.status_code not in (301, 302, 303, 307, 308) or not location:
            raise InputRefused("That short link didn't lead to a Google Maps place.")
        current = urljoin(current, location)
    raise InputRefused("That short link redirects too many times.")


DOH_ENDPOINTS = (
    ("https://dns.google/resolve", {}),
    ("https://cloudflare-dns.com/dns-query", {"Accept": "application/dns-json"}),
)
_pin_lock = threading.Lock()


def doh_resolve(host: str, timeout: float = 5) -> list[str]:
    """IPv4 addresses for a host from public DNS-over-HTTPS resolvers (plain HTTPS, never SerpApi)."""
    for endpoint, headers in DOH_ENDPOINTS:
        try:
            resp = requests.get(endpoint, params={"name": host, "type": "A"}, headers=headers, timeout=timeout)
            answers = resp.json().get("Answer") or []
        except (requests.RequestException, ValueError):
            continue
        ips = [a["data"] for a in answers if a.get("type") == 1 and a.get("data")]
        if ips:
            return ips
    return []


def fetch_pinned(url: str, ip: str, headers: dict[str, str], timeout: float) -> requests.Response:
    """GET a URL while connecting to a given IP. SNI and certificate checks still use the URL's hostname."""
    import urllib3.util.connection as u3conn

    host = urlsplit(url).hostname
    original = u3conn.create_connection

    def pinned(address, *args, **kwargs):
        target, port = address
        return original((ip if target == host else target, port), *args, **kwargs)

    with _pin_lock:
        u3conn.create_connection = pinned
        try:
            with requests.Session() as fresh:
                return fresh.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        finally:
            u3conn.create_connection = original


def _fetch_via_doh(url: str, headers: dict[str, str], timeout: float) -> requests.Response | None:
    host = urlsplit(url).hostname or ""
    for ip in doh_resolve(host):
        try:
            return fetch_pinned(url, ip, headers, timeout)
        except requests.RequestException:
            continue
    return None


def parse_input(text: str, session: requests.Session | None = None) -> ResolvedInput:
    """Classify user input. Only a short link touches the network (plain HTTP, never SerpApi)."""
    text = (text or "").strip()
    if not text:
        raise InputRefused("Paste a Google Maps link, or type a business name and city.")
    if _looks_like_url(text):
        url, parts = _split(text)
        if _is_short(parts):
            target = expand_short_link(url, session)
            resolved = parse_maps_url(target)
            resolved.expanded_from = url
            return resolved
        return parse_maps_url(url)
    if len(text) < 3:
        raise InputRefused("Type a business name and city, e.g. 'Sunrise Dental Clinic, Pune'.")
    return ResolvedInput(kind="name", cost=1, query=text)


def lookup_request(resolved: ResolvedInput) -> catalog.SerpRequest | None:
    """The SerpApi request needed to identify the place, or None when the input already does."""
    if resolved.kind == "data_id":
        return None
    if resolved.kind == "cid":
        return catalog.place_by_cid(resolved.cid or "")
    if resolved.kind == "place_id":
        return catalog.place_by_place_id(resolved.place_id or "")
    return catalog.place_search(resolved.query or "")


def _gps(item: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = item.get("gps_coordinates") or {}
    lat, lng = gps.get("latitude"), gps.get("longitude")
    return (float(lat) if lat is not None else None, float(lng) if lng is not None else None)


def _candidate(item: dict[str, Any]) -> PlaceCandidate:
    lat, lng = _gps(item)
    data_id = item.get("data_id")
    return PlaceCandidate(
        data_id=data_id.lower() if isinstance(data_id, str) else None,
        place_id=item.get("place_id"),
        title=item.get("title"),
        address=item.get("address"),
        type=item.get("type"),
        rating=item.get("rating"),
        reviews=item.get("reviews"),
        lat=lat,
        lng=lng,
    )


def candidates_from_body(body: dict[str, Any]) -> list[PlaceCandidate]:
    if body.get("place_results"):
        return [_candidate(body["place_results"])]
    limit = config.tunable("resolve", "name_search_candidates")
    return [_candidate(item) for item in (body.get("local_results") or [])[:limit]]


def lookup(gateway: Gateway, resolved: ResolvedInput, analysis_id: str | None = None) -> list[PlaceCandidate]:
    """Run the one lookup search (or serve it from cache). Callers confirm the cost first."""
    req = lookup_request(resolved)
    if req is None:
        return [
            PlaceCandidate(resolved.data_id, None, None, None, None, None, None, resolved.lat, resolved.lng),
        ]
    resp = gateway.fetch(req, analysis_id=analysis_id)
    return candidates_from_body(resp.body)


def target_coords_request(data_id: str) -> catalog.SerpRequest:
    """Fallback when no fetched history contains the target: 1 lookup by data_cid (spec 8)."""
    return catalog.place_by_cid(catalog.data_cid_from_data_id(data_id))

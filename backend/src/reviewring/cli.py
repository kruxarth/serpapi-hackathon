"""Command-line interface. Built from M1 so user checkpoints run before the API exists.

Nothing here spends a search without ``--yes``, and every command shows the
estimated cost and the remaining budget first.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections import Counter
from typing import Any

from . import config, db, redact
from .resolve import InputRefused, lookup, lookup_request, parse_input
from .serp import catalog
from .serp.errors import GatewayError, NotCached
from .serp.gateway import Gateway, PlannedRequest, pages_needed

log = logging.getLogger("reviewring")


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _budget_line(gw: Gateway) -> str:
    s = gw.budget_status()
    src = "ledger + Account API" if s.account else "local ledger only"
    return f"Budget ({src}): {s.month_remaining} searches left this month, {s.hour_remaining} this hour."


def _gateway(args: argparse.Namespace, dry_run: bool = False) -> Gateway:
    return Gateway(mode="offline" if getattr(args, "offline", False) else "live", dry_run=dry_run)


# --------------------------------------------------------------------------- budget


def cmd_budget(args: argparse.Namespace) -> int:
    gw = _gateway(args)
    account = None
    if gw.mode == "live":
        account = gw.refresh_account()  # free: doesn't count toward the quota
    status = gw.budget_status()
    if args.json:
        _print(status.as_dict())
        return 0
    print(_budget_line(gw))
    print(f"Local ledger: {status.ledger_month} billed this month, {status.ledger_hour} in the last 60 minutes.")
    print(f"Caps: {status.monthly_cap}/month, {status.hourly_cap}/hour, {status.per_analysis_cap}/analysis.")
    if account:
        for key in (
            "plan_name",
            "total_searches_left",
            "plan_searches_left",
            "this_month_usage",
            "this_hour_searches",
            "last_hour_searches",
            "account_rate_limit_per_hour",
            "plan_renewal_date",
        ):
            if key in account:
                print(f"  {key}: {account[key]}")
    return 0


# --------------------------------------------------------------------------- resolve


def cmd_resolve(args: argparse.Namespace) -> int:
    resolved = parse_input(args.input)
    out: dict[str, Any] = {k: v for k, v in resolved.__dict__.items() if v is not None}
    req = lookup_request(resolved)
    gw = _gateway(args)
    if req is not None:
        cached = gw.lookup_cache(req)
        out["lookup_cached"] = cached is not None
        out["cost"] = 0 if cached else 1
        if cached or args.yes:
            out["candidates"] = [c.__dict__ for c in lookup(gw, resolved)]
        else:
            out["note"] = "Identifying this place costs 1 search. Re-run with --yes to spend it."
            out["budget"] = _budget_line(gw)
    else:
        out["data_cid"] = catalog.data_cid_from_data_id(resolved.data_id or "")
    _print(out)
    return 0


# --------------------------------------------------------------------------- probe


def _shape(items: list[dict[str, Any]]) -> dict[str, int]:
    """How many items carry each key (and each nested key one level down)."""
    counts: Counter[str] = Counter()
    for item in items:
        for key, value in item.items():
            counts[key] += 1
            if isinstance(value, dict):
                for sub in value:
                    counts[f"{key}.{sub}"] += 1
    return dict(sorted(counts.items()))


def _pick_reviewer(reviews: list[dict[str, Any]]) -> str | None:
    """The 5-star reviewer with the fewest total reviews (unknown counts last)."""
    best: tuple[int, int, str] | None = None
    for index, review in enumerate(reviews):
        user = review.get("user") or {}
        cid = user.get("contributor_id")
        if not cid or review.get("rating") != 5:
            continue
        total = user.get("reviews")
        key = (total if isinstance(total, int) else 10**9, index, str(cid))
        if best is None or key < best:
            best = key
    return best[2] if best else None


def cmd_probe(args: argparse.Namespace) -> int:
    """A0 shape probe: page 1 of reviews + one reviewer's history (~2-3 searches)."""
    resolved = parse_input(args.input)
    plan_gw = Gateway(mode="offline", dry_run=True)
    data_id = resolved.data_id
    estimate = 0
    lookup_req = lookup_request(resolved)
    if lookup_req is not None and plan_gw.lookup_cache(lookup_req) is None:
        estimate += 1
    page1 = catalog.reviews_page(data_id) if data_id else None
    page1_cached = plan_gw.lookup_cache(page1) if page1 else None
    if page1_cached is None:
        estimate += 1
    history_cached = False
    if args.contributor:
        history_cached = plan_gw.lookup_cache(catalog.contributor_history(args.contributor)) is not None
    elif page1_cached is not None:
        picked = _pick_reviewer(page1_cached.body.get("reviews") or [])
        if picked:
            history_cached = plan_gw.lookup_cache(catalog.contributor_history(picked)) is not None
    if not history_cached:
        estimate += 1

    gw = _gateway(args, dry_run=args.dry_run)
    if gw.live:
        gw.refresh_account()
    print(f"Probe estimate: at most {estimate} search(es). {_budget_line(gw)}")
    if args.dry_run:
        print("Dry run: nothing will be requested.")
    elif estimate and not args.yes:
        print("Re-run with --yes to spend them.")
        return 2

    analysis_id = f"probe-{db.iso(db.utcnow())}"
    report: dict[str, Any] = {"input_kind": resolved.kind}
    try:
        if data_id is None:
            candidates = lookup(gw, resolved, analysis_id)
            if len(candidates) != 1 or not candidates[0].data_id:
                _print({"candidates": [c.__dict__ for c in candidates]})
                print("Pick one candidate and re-run the probe with its data_id or link.")
                return 2
            data_id = candidates[0].data_id
        report["data_id"] = data_id
        report["data_cid"] = catalog.data_cid_from_data_id(data_id)

        page = gw.fetch(catalog.reviews_page(data_id), analysis_id=analysis_id)
        reviews = page.body.get("reviews") or []
        report["reviews_page1"] = {
            "from_cache": page.from_cache,
            "status": page.status,
            "search_id": page.search_id,
            "top_level_keys": sorted(page.body.keys()),
            "place_info_keys": sorted((page.body.get("place_info") or {}).keys()),
            "review_count": len(reviews),
            "has_next_page_token": bool((page.body.get("serpapi_pagination") or {}).get("next_page_token")),
            "review_key_counts": _shape(reviews),
        }

        contributor = args.contributor or _pick_reviewer(reviews)
        if not contributor:
            print("No 5-star reviewer with a contributor_id on page 1. Pass --contributor to pick one.")
        else:
            hist = gw.fetch(catalog.contributor_history(contributor), analysis_id=analysis_id)
            items = hist.body.get("reviews") or []
            report["history"] = {
                "from_cache": hist.from_cache,
                "status": hist.status,
                "search_id": hist.search_id,
                "top_level_keys": sorted(hist.body.keys()),
                "contributor_keys": sorted((hist.body.get("contributor") or {}).keys()),
                "review_count": len(items),
                "review_key_counts": _shape(items),
                "sample_dates": [i.get("date") for i in items[:15]],
                "contains_target": any(
                    str((i.get("place_info") or {}).get("data_id", "")).lower() == data_id for i in items
                ),
            }
    except NotCached as exc:
        print(f"Dry run: {exc}")
    except (GatewayError, InputRefused) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        if gw.planned:
            print("Would request:")
            for p in gw.planned:
                print(f"  - {p.label} ({p.engine}), {p.cost} search")

    if gw.live and gw._account:
        report["plan_renewal_date"] = gw._account.data.get("plan_renewal_date")
    _print(report)
    print(_budget_line(gw))
    return 0


# --------------------------------------------------------------------------- dry run


def cmd_dry_run(args: argparse.Namespace) -> int:
    """List exactly which requests an analysis would make, using the cache only."""
    n = args.n or config.tunable("collection", "n_reviews")
    k1, b, k2 = (config.tunable("collection", k) for k in ("k1", "baseline", "k2"))
    resolved = parse_input(args.input)
    gw = Gateway(mode="offline", dry_run=True)
    minimum = maximum = 0
    data_id = resolved.data_id
    if data_id is None:
        try:
            candidates = lookup(gw, resolved)
            data_id = candidates[0].data_id if len(candidates) == 1 else None
        except NotCached:
            pass
    if data_id:
        pages = gw.fetch_pages(data_id, n)
        print(f"Review pages: {len(pages.responses)} cached of {pages_needed(n)} needed.")
    else:
        gw.planned.append(
            PlannedRequest(
                "reviews pages (after the place is identified)", catalog.REVIEWS_ENGINE, None, pages_needed(n)
            )
        )
    for p in gw.planned:
        minimum += p.cost
        maximum += p.cost
    rounds = f"round 1: {k1 + b} reviewer histories" + ("" if args.stop_after_round1 else f", round 2: up to {k2} more")
    maximum += k1 + b + (0 if args.stop_after_round1 else k2)
    minimum += k1 + b
    print("Would request:")
    for p in gw.planned:
        print(f"  - {p.label} ({p.engine}), {p.cost} search{'es' if p.cost != 1 else ''}")
    print(f"  - {rounds} (chosen after scoring; cached histories cost nothing)")
    cap = config.tunable("budget", "per_analysis_cap")
    print(f"Estimate: {minimum}-{min(maximum, cap)} searches (per-analysis cap {cap}). {_budget_line(gw)}")
    return 0


# --------------------------------------------------------------------------- housekeeping


def cmd_ledger(args: argparse.Namespace) -> int:
    conn = db.connect()
    rows = conn.execute(
        "SELECT timestamp, engine, status, search_id, analysis_id FROM ledger ORDER BY id DESC LIMIT ?", (args.limit,)
    ).fetchall()
    for r in rows:
        print(
            f"{r['timestamp']}  {r['engine']:<34} {r['status']:<6} {r['search_id'] or '-'}  {r['analysis_id'] or '-'}"
        )
    if not rows:
        print("The ledger is empty: no searches have been made.")
    return 0


def cmd_purge_data(args: argparse.Namespace) -> int:
    target = config.data_dir()
    if not args.yes:
        print(f"This deletes everything in {target} (cache, ledger, case list, pseudonym salt). Re-run with --yes.")
        return 2
    shutil.rmtree(target)
    print(f"Deleted {target}.")
    return 0


# --------------------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reviewring", description="ReviewRing command-line interface")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("budget", help="Show the search budget (Account API is free)")
    p.add_argument("--offline", action="store_true", help="Local ledger only; no network")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("resolve", help="Parse a link or name; a lookup (1 search) only with --yes")
    p.add_argument("input")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("probe", help="Checkpoint A0: page 1 of reviews + one reviewer history (~2-3 searches)")
    p.add_argument("input")
    p.add_argument("--contributor", help="contributor_id to expand (default: 5-star reviewer with fewest reviews)")
    p.add_argument("--yes", action="store_true", help="Actually spend the searches")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("dry-run", help="List the requests an analysis would make (cache only, no network)")
    p.add_argument("input")
    p.add_argument("--n", type=int)
    p.add_argument("--stop-after-round1", action="store_true")
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("ledger", help="Show recent live requests")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("purge-data", help="Delete everything in data/ (it holds personal data)")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_purge_data)
    return parser


def main(argv: list[str] | None = None) -> int:
    redact.install()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    for value in config.load_secrets().values():
        redact.register_secret(value)
    try:
        return args.func(args)
    except (GatewayError, InputRefused) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - last line of defence: never print a raw HTTP error
        print(f"Unexpected error: {redact.safe_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

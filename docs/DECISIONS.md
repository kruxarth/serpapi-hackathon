# Decisions

One line of reasoning per decision not fixed by IMPLEMENTATION.md.

- **Backend layout:** `backend/` is a uv project with a `src/reviewring` package and `tests/`; the CLI entry point is `reviewring`. Standard uv layout.
- **Tunables file:** all *(tunable)* values live in `config/reviewring.toml`; a gitignored `data/config.toml` may override any of them locally. One committed source of truth, per spec section 0.
- **Ledger status column:** the ledger also records each request's outcome (`ok`, `empty`, `error`); only `ok` and `empty` count toward the local caps, because SerpApi bills neither errors nor failures but does bill empty results.
- **Account email:** it is stripped before anything is stored (Rule 4). The leak check therefore rejects any email address at all, which covers the account email without keeping a copy of it.
- **Raw responses for errors:** HTTP errors (401/429/5xx) are stored in `raw_responses` with status `error` for debugging but are never served as cache hits.
- **Frozen page sizes:** `num` values (8 / 20 / 200) are constants in `serp/catalog.py`, not tunables, so a config change can never silently change request keys and orphan the cache.
- **Place lookup parameters:** single-place lookups send only `data_cid` or `place_id` (plus `hl=en`); SerpApi's docs say `type` isn't required with either. Name searches send `type=search`.
- **Short-link expansion** uses `requests` with `allow_redirects=False` and follows each hop manually, so loops, the hop limit and consent pages are all handled explicitly.
- **Pagination failure:** a 429 or a repeated 5xx mid-pagination returns the pages already fetched with a note, instead of pausing between pages (spec 5.3 forbids pauses inside pagination).
- **IMPLEMENTATION.md** is left uncommitted until the user decides whether the internal spec belongs in the public repo.
- **Hourly cap stays 50:** the Account API reports `account_rate_limit_per_hour = 250` for this account, but the spec's free-plan figure (50) is kept as the configured cap because it's stricter.
- **Engine as a pure function:** collection produces an `AnalysisInput`; the engine never fetches. Demo mode, the CLI `analyze` command and the evaluation harness all run the same `analyze()`.
- **Text clusters are anchored on target reviews:** similarity is computed for (target review, any text) pairs, not all history pairs, which is all A6, T4 and stock phrases need and keeps it fast.
- **Priority uses target-only clusters:** the priority score's duplicate-cluster points use clusters among the target's reviews only, so the expansion order never depends on histories fetched later.
- **Pruning removes one member at a time** (the weakest first), so one removal can't cascade unfairly.
- **Offline mode analyses whatever is cached** and reports what's missing with its cost, instead of failing on the first missing history.
- **Member-signals confidence part** counts only non-context signals (A1, A2, A5, A6, A7); A3, A4 and A8 are context only.
- **Label precedence:** ring > possible ring (trip-like) > suspicious > group trip > no flags. Copied text is independent evidence, so it outranks the neutral trip explanation.
- **A ruled-out trip is reported** only when it has at least 3 members and 2 core places; smaller overlaps aren't worth a card.
- **`fake_serp.py`** serves a synthetic world as real-shaped SerpApi JSON, so live mode can be exercised end to end without spending searches.

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
- **Fixtures store the pseudonymized engine input** plus the report the engine produces from it; demo mode re-runs the engine, and a test checks the re-run equals the stored report.
- **Synthetic demo fixtures** (`fixtures/synthetic-*.json`, made by `reviewring demo-fixtures`) let demo mode work on a fresh clone before real showcases exist. They are labelled "synthetic" in every view.
- **Leak check scope:** phone and PIN rules apply to free-text strings only; numbers, ISO timestamps and the exporter's salted ids are exempt, since the PIN pattern otherwise fires on microseconds and hex hashes.
- **Presentation mode is server-side:** the API pseudonymizes reports when asked (`?presentation=1`), so real names never reach the browser in a recording.
- **Evaluation bases fall back to synthetic businesses** until real clean controls are cached (listed in `data/cases.toml`); the results say which kind of base was used.
- **Collection is simulated in evaluation:** the harness replays the priority score, round 1, the early stop and round 2 on the combined data, so "not chosen" losses are real losses of the budgeted method.
- **Extra "harder rings" table** (aged accounts with photos, unique texts, spread timing) is information only; it shows where the method loses rings, since planted rings otherwise follow our own model.
- **DeepSeek model is `deepseek-flash`** (checked against api-docs.deepseek.com on 2026-09-29; `deepseek-chat` in the first draft of the config was from memory). JSON mode via `response_format: json_object`; prompts say "json" as the docs require.
- **LLM client is a thin `requests` call** to the OpenAI-compatible `/chat/completions` endpoint rather than the `openai` package: one fewer dependency, and the key only ever travels in an Authorization header.
- **Place-name validator** uses states, UTs, metro aliases and a config list of major Indian cities, plus the analysis's own areas.
- **Template summary always attached** when no validated LLM text exists, so the report shape is the same with or without a key.

## After the external design review (2026-10-04)

- **Home areas:** a reviewer's home is the most common area among places no other checked reviewer reviewed. Surprise distance is the nearer of the business and either reviewer's home, so hometown friends reviewing a far business don't look like a multi-city ring.
- **Social circle verdict:** at least half the members share a home area and at least half the core places are within 50 km of it. Neutral, never counted.
- **Trips are ruled out only on positive evidence** (a shared home area, or hotel review details saying family/friends/couple) plus 2 of 3 trip indicators. Otherwise trip evidence caps a group at "possible ring-like (trip-like)". The old rule hid 61% of planted regional campaigns in the ablation.
- **One non-travel core place** (an emporium, a pharmacy) no longer breaks the trip shape when there are 3 or more core places.
- **Batch priority feature:** +2 for a 5-star review with at least 2 other 5-star reviews within 24 hours, outside a detected burst. It catches small batches a busy place's burst test misses.
- **Stock phrases are judged among checked users only;** with fewer than 3 checked users the phrase is undetermined and kept as evidence, so a mass farm template isn't dismissed.
- **Free date calibration:** the report lists each checked reviewer's (relative string, true date) pair for their review of this business.
- **Privacy:** fixtures and presentation mode shift all dates by a hidden per-business offset (30–365 days), show the review count to one significant figure, and round coordinates to 1 decimal.
- **Wording:** "ring-like group", "evidence strength (not a probability)", "excluding linked reviewers", "other places this group reviewed", a standing caveat that a business can be targeted without its knowledge, and a neutral badge on Maps pages.
- **Deferred until real data:** the reverse co-client lookup (finds aged ring accounts from one seed, but spends searches), a degree-preserving shuffle (curveball) p-value, route-order trip checks, and building the popular-type list from real type strings.
- **Single-use-account bursts (after the first real data, 2026-10-04):** a burst with ≥ 5 reviews from accounts showing ≤ 1 review, making up ≥ 60% of it, gets the label "single-use account in a burst" and raises the level to at least Elevated (never High). Real Bengaluru mover listings used burner accounts that the graph method can't connect, so this is the deliberate exception to "bursts never raise the level on their own". It's switchable in config (`single_use.raises_level`).
- **Hourly cap:** the account reports 250 searches/hour, so a local, gitignored `data/config.toml` raises our cap to 200; the committed default stays at the spec's 50.

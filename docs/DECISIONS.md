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
- **Rating gap and top-rated sample (after real data, 2026-10-04):** when the displayed rating is ≥ 0.8★ above the newest reviews and the total is ≥ 5× the sample, the collector fetches 3 pages sorted by highest rating (3 searches). The report then shows what the older reviews must average and when the top-rated reviews were posted. A real Delhi hotel showed 4.9★ from 6,607 reviews while its latest 88 averaged 3.31★.
- **Generated-text markers:** a fixed phrase list (chatbot replies such as "unable to generate a review", unfilled placeholders such as "[Hotel Name]"). A match raises the level to at least Elevated (never High), since no customer writes those phrases. Fixtures keep the matched phrase, never the text. *(Superseded for excerpts, see below.)*
- **Per-analysis cap 35:** 5 pages + 25 histories + 3 top-rated + 1 coordinates lookup.
- **The synthetic World's displayed rating defaults to unknown,** so random synthetic ratings don't trigger the gap check.

## Evidence-first interface (2026-10-04)

- **Reviewer histories in the report:** `report.histories` carries each checked reviewer's visible history in compact form (approximate day, stars, area, type group, distance from the business, coordinates to 2 decimals, place key). The reviewer profile, the strips under "Reviewers opened" and the replay read it; nothing in the browser scores it. Presentation mode and fixtures hash its ids, shift its dates and round its coordinates to 1 decimal like the rest of the report.
- **Chatbot excerpts are kept:** for a review that matches a generated-text marker, the report keeps up to 240 characters around the phrase (`excerpt`); presentation mode and fixtures scrub it (links, emails, phones, handles, business-name words) and cut it to 180. The text was written by a machine and it is the evidence; other review texts stay dropped.
- **Live-view events:** the collector also emits `reviews_loaded`, `picks`, `history` and `links` events. They carry stars, day offsets, review counts and indices into the sample, never ids, names or places, so they are safe on screen in a recording. The UI plays them at a minimum pace, so a run served from cache still reads as an investigation, and a finished report can be replayed from the same shapes at no cost.
- **The verdict's running average** eases from Google's figure into the plain average of the dots over the first fifth of them, then is exact and lands on the report's own figure; the caption says "averaging", not "the average so far".
- **T6 and T8 review ids** are now hashed in presentation mode too (they were passed through unchanged).

## Warning signs, sorting and the reader's choice (2026-10-07)

- **Reposition around per-review signs.** Real data showed cheap, one-at-a-time manipulation (first-time accounts in bursts, pasted chatbot replies), not rings. Each review now gets every sign that applies (`engine/signs.py`), and the reader chooses which to set aside. Rings stay as one sign ("linked reviewer group"), not the headline.
- **Sign order and defaults** live in config (`[signs]`): chatbot text, copied text, first-time burst, linked group (strong, set aside at first); reads as AI-written (opinion, kept); reviewing spree and first-time account (context, kept). A review is drawn in the first set-aside branch; the level never depends on the reader's choice.
- **A single first-time account is context, not a sign of anything.** Real clean listings have 15–20% of 5★ reviews from accounts with no other reviews. The aggregate test is the existing burst rule plus a first-time skew finding (5★ at least twice as likely to be first-time as other reviews, ≥ 35% of 5★), after Xie et al. (KDD 2012). The 35% floor was added after the clean real mover fired the skew at 20% vs 0%.
- **Newest 100 reviews:** 6 pages (8 + 5 × 20 = 108), trimmed to the newest 100 so "X of the newest 100" reads cleanly; one more search per analysis, per-analysis cap 36. Cached 5-page analyses still re-run offline on 88 and note the missing page.
- **AI-written opinion (LLM job 3, `ai-style-v1`):** only reviews with ≥ 40 words (detectors fail on short text and over-flag second-language writers); scrubbed texts in batches of 12 with opaque indices; an "AI-written" verdict needs ≥ 2 quoted phrases that occur in the scrubbed text, else "unclear". Kept by default, shown with its quotes, never raises the level. Stored in `AnalysisInput.text_judgements` so the engine stays pure and fixtures carry it. Pangram's detector is the strongest third-party option but costs about $0.05 per review at this length, so it isn't wired in.
- **Reviewing spree (A9, context):** a checked reviewer's busiest 31-day window holds ≥ 8 non-popular places in ≥ 3 areas, ≥ 90% 5★. The real hotel's task-worker-like account now shows it.
- **No search counts for users.** The cost estimate, "searches left" chip and "searches used" panels are gone from the web app and the extension; budget and caps live under Settings and a "For developers" section of the report. The extension still never fetches without the "Check reviews" click.
- **Synthetic demo worlds for the common patterns:** `synthetic-movers` (31 reviews in 3 days, 27 from first-time accounts, a copied template, AI-styled texts, a pasted chatbot reply) and `synthetic-hotel` (shows 4.8★, newest 100 average ~3.2, an old batch of first-time 5★ reviews, a reviewing spree). Their AI opinions are written with the invented texts (labelled "synthetic example"), because demo mode never calls a model, and synthetic fixtures keep their invented texts in full.
- **Presentation mode** still hides ordinary review texts; the AI opinion's quoted phrases are kept, scrubbed and cut to 60 characters each, like chatbot excerpts.
- **DeepSeek thinking is off (`[llm] thinking = "disabled"`), and empty replies are never stored.** On the first live run `deepseek-flash` (thinking on by default, at high effort) returned empty JSON for 8 of 10 calls, and the empty replies were cached. Empty replies now raise `EmptyReply`, are retried once and never stored; a stored empty reply counts as missing. With thinking off, every long-enough review on the three real listings was judged. Quotes that cross a scrubbed span ("[business]") still count towards the verdict but aren't shown, since they can't be found in the original text.
- **What the AI opinion showed on real listings (2026-10-07):** the burst movers' 4 "AI-written" reviews are all 5★ from first-time accounts; the hotel's 5 are mostly 1–3★ complaints, real guests polishing honest complaints. It stays an opinion, kept by default.

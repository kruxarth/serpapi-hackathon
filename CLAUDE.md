# Notes for agents working on ReviewRing

SerpApi India Hackathon 2026 entry (Knowledge & Public Interest track). Submission deadline **2026-10-10 23:59 IST**.
Read `docs/SYSTEM-OVERVIEW.md` for the algorithm, `docs/DECISIONS.md` for why things are the way they are.

## Hard rules (from the original spec; still binding)

- **Never spend SerpApi searches** unless the user asks at that moment. The free Account API is the only exception. The whole hackathon has ~250 searches; check `/api/budget` (`month_remaining`) before and after anything risky.
- **No live DeepSeek calls** unless asked. The LLM only writes a summary; it never decides a label, level or rating.
- **No personal data in git.** `data/` is gitignored: cache DB, ledger, pseudonym salt, `data/demo-script.md` (names real listings). `IMPLEMENTATION.md` is also gitignored. Committed data is only the pseudonymized `fixtures/`, which must pass `python -m reviewring.leakcheck fixtures`.
- **Never name real listings** in tracked files, the README, or anything shown on screen in presentation mode.
- Wording: "suspicious", "coordinated", "ring-like". Never "fake", "fraud" or "scam" about a business or person. Reviews are "set aside" or "kept", never removed as fake.
- No search counts or API costs in anything a user sees (web app or extension). They belong under Settings and the report's "For developers" section.
- Backend binds to 127.0.0.1 only. Keys never leave the backend or appear in logs.
- Small descriptive commits; don't rewrite history. Commit only when the user asks.

## Running and checking

- Build the web app, then serve it from the backend:
  `cd web && npm run build` then `cd backend && uv run reviewring serve` → http://127.0.0.1:8765
- With a SerpApi key in `.env` the app is in **live** mode. Without one it is in **demo** mode (synthetic fixtures only). Live mode still serves cached data at 0 searches.
- **Zero-search verification before starting any analysis:** `POST /api/resolve` (header `X-ReviewRing: 1`) with `{"input": ..., "stop_after_round1": true}` and check `estimate.min == estimate.max == 0`. A long `data=!…!1s0x…` URL may show max 1 for the coordinates lookup, but that is free when a cached history contains the target.
- `maps.app.goo.gl` short links take ~20 s to resolve (DNS fallback), at no search cost. The long URL is instant.
- `uv run reviewring analyze <analysis_id>` re-runs the engine on a stored analysis from cache (offline, 0 searches). Run it on stored analyses after changing the report shape, or old reports lack the new fields.
- `uv run reviewring demo-fixtures` regenerates `fixtures/synthetic-*.json`. Needed after any report-shape change: `test_committed_fixtures_pass_leak_check_and_rerun` requires the stored report to equal a re-run.
- Backend checks: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` (line length 120). Tests block any network call.
- Web checks: `npx tsc -b`, `npx oxlint` (the "only-export-components" and `Date.now` purity warnings were already there), `npm run build`.
- Screenshots: install `playwright-core` in the scratchpad and launch it with `executablePath: '/usr/bin/google-chrome-stable'`, then wait for animations. Plain `chrome --headless --screenshot` misses in-view animations, and charts look empty.

## Privacy plumbing (any new report field must go through it)

- Presentation mode is server-side: `?presentation=1` makes the API return `privacy.pseudonymize_report(report)`. It hashes ids, renames places, shifts dates by a hidden per-business offset, rounds coordinates to 1 decimal, and blurs counts.
- Fixtures are pseudonymized at the *input* level in `exporter.pseudonymize_input`.
- A new field with contributor ids, place keys, dates, coordinates or text needs handling in both places, plus a test in `backend/tests/test_review_fixes.py`.
- Chatbot or placeholder review text is the one kept text: `excerpt`, scrubbed and cut to 180 chars when pseudonymized.

## Report and event shapes added on 2026-10-04

- `report.histories[contributor_id]`: `{total_reviews, visible, home_area, items: [{day, rating, place_key, this, area, type_group, lat, lng, km}]}`.
- `reviews[].excerpt` and `signals.T8.generated[].excerpt`: text around a chatbot or placeholder phrase.
- Live progress events from `collect.py` (`Collector.show`): `reviews_loaded`, `picks`, `history`, `links`. They carry stars, day offsets, counts and review indices only, never ids or names. The UI plays them at a minimum pace (`usePlayback` in `web/src/components/Investigation.tsx`), and `eventsFromReport` rebuilds the same events from a finished report for the free replay.
- Google's profile review count (`total_reviews`) can be *lower* than the number of reviews the API returns. The UI shows `max(total, visible)`.

## Report shapes added on 2026-10-07 (warning signs)

- `reviews[].signs` (sign keys in sieve order), `reviews[].ai` (`{verdict, cues}` or null), `report.sieve` (`order`, `set_aside_by_default`, `signs{name, short, strength, explain, count, mean}`, `kept`, `no_signs`, `all`, `ai` coverage), `ratings.kept_mean/kept_count`, `signals.T9` (first-time skew), badge `A9` (reviewing spree).
- `AnalysisInput.text_judgements[review_id] = {verdict, cues, model}` holds the LLM's AI-written opinion; `report.store_report` fills it in live mode (cached by payload hash), the exporter hashes its keys and scrubs its cues. Synthetic worlds write theirs in `demo_fixtures.synthetic_judgements`.
- The sample is now 100 reviews (6 pages). Analyses cached with 5 pages re-run offline on 88 and list the missing page.

## Frontend map

- `components/Sieve.tsx`: `useSieve(report)` (the reader's set-aside choice, shared by the verdict ladder and the list) and `SieveGraph` (vertical flow: newest reviews → one row per sign → Kept; each review is a dot that moves when a sign is toggled).
- `components/ReviewList.tsx`: `BranchTabs` and the review cards behind a branch, with the AI opinion's quoted phrases underlined.
- `components/RatingUnpacked.tsx`: dots stacked by star with flagged reviews lifted into a tray. Only the home hero uses it now (`illustrationDots()`).
- `components/Investigation.tsx`: the live analysis view and the replay.
- `components/Reviewer.tsx`: `ReviewerProvider`/`useReviewer().open(cid)` opens the profile drawer (radar, timeline, cities). Also has `HistoryStrip` and `CheckedGrid`.
- `components/Findings.tsx`: one visual per evidence kind. `ReviewCard` types out chatbot text.
- Gotcha: **motion can't interpolate CSS-variable or `color-mix()` colours.** Set them as SVG attributes or plain styles and let a CSS `transition` ease them. Animating them through motion silently fails (the old home hero's dots never appeared because of this).
- Design rule: star gold (`--gold`) means rating and nothing else. Label colours: ring orange, suspicious blue, trip green.

## What the real data showed (keeps claims honest)

- About 100 real searches were spent on Bengaluru and Delhi listings. Real findings are a **burst of single-use accounts** (a mover) and a **rating carried by old reviews, plus chatbot text** (a hotel). Numbers are in the README.
- **No rings were found in the real sample.** Ring visuals and claims must be labelled synthetic.
- `docs/demo.html` is a standalone ~1:46 "video" demo. `#<seconds>` or `#<chapter-slug>` deep-links into it, and **H** hides the controls for screen recording.

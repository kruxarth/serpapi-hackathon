# ReviewRing

**A Google rating is a number. ReviewRing shows where it comes from.** Paste a Google Maps link and ReviewRing checks who wrote the reviews, when, and whether those accounts look like real customers. Every finding comes with the evidence behind it.

It runs five checks:

| Check | What it catches |
|---|---|
| **Bursts of single-use accounts** | Dozens of 5★ reviews in a few days from accounts that have reviewed nothing else |
| **Chatbot and template text** | Reviews that say "I'm unable to generate a review for you…" or "[Hotel Name]" |
| **A rating carried by old reviews** | A listing showing 4.9★ while its recent guests average 3.3★ |
| **Linked reviewer groups** | Accounts that reviewed the same unrelated businesses in distant cities (with group trips and friends ruled out) |
| **Waves of prompted reviews** | Shown as context, never as a red flag: asking real customers is not the same as buying reviews |

![A ReviewRing report (synthetic example, pseudonymized)](docs/screenshots/report.png)

*SerpApi India Hackathon 2026 · Knowledge & Public Interest track · MIT licensed*

## What we found on real listings

We tested ReviewRing on real Google Maps listings in Bengaluru and Delhi (about 100 SerpApi searches). The manipulation we found was cheaper than we expected:

- **Burner accounts:** a mover rated 5.0★ received 31 five-star reviews in 3 days; 27 came from accounts that have never reviewed anything else.
- **Chatbot text:** a budget hotel showing 4.9★ from thousands of reviews, whose latest 88 reviews average 3.3★, had a 5★ review reading *"I'm unable to generate a review for you, but I can help you outline key points."*
- **No rings in this sample.** Even an account that looked like a "rate hotels and earn" task worker (12 hotels in 6 cities in one month, all 5★) shared no hotels with other reviewers. In those scams the hotels are decoys and each worker gets a different list, so the linked-group check stays in the product but isn't the headline.
- **Reviews that look like a campaign but aren't one:** a mover whose reviews arrive in waves was rated Low, because the reviewers' full histories showed established local people. The business was asking customers to review, not buying reviews.

Listings are not named here; the tool reports patterns, not verdicts.

## The problem

People in India pick clinics, hotels, coaching centres, packers-and-movers and restaurants by their Google rating. That rating is distorted by paid review farms, and by the "rate hotels on Google Maps and earn" **task scams**, which recruit ordinary people to post 5★ reviews in batches (see [The Metrognome](https://www.themetrognome.in/business-and-personal-finance/are-you-receiving-data-entry-job-offers-its-likely-an-online-scam) and a [₹9.68 lakh task-fraud case reported by Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fmaharashtra%2Ffour-held-for-cheating-media-executive-of-rs-968-lakh-in-task-fraud-in-mumbai-2691525)).

A single bought review is indistinguishable from a real one. The pattern only appears in aggregate: when the reviews arrived, who wrote them, what else those accounts have reviewed, and whether the recent reviews agree with the displayed rating.

## How it works

1. **Newest reviews.** Fetch the business's newest 88 reviews and score each reviewer by how likely a closer look is to pay off (review bursts, thin profiles, near-duplicate texts).
2. **Reviewer histories.** Fetch the full public history of the 8 highest-priority reviewers plus 2 random baseline reviewers. If none of them share anything, stop there. Otherwise fetch 15 more.
3. **Co-review graph.** Link two reviewers when they reviewed at least two of the same *unrelated, distant* places, weighted by distance from the business and by how unusual the place type is.
4. **Groups, not individuals.** Find tight groups and set aside the innocent ones: **friends and family** (most members share a home area, near the places they share) and **group trips** with positive evidence (a shared home, or hotel reviews saying family or friends). A group is called ring-like only when it spans several distant cities. Distances are measured from the business *and* from each reviewer's home, so friends from Pune don't look suspicious just because the business is in Goa.
5. **Evidence first.** The report shows the suspicion level with its reasons, the rating excluding linked reviewers, the reviewer-link graph, a map of where the group's other reviews are, a timeline of review bursts, **the other places this group reviewed**, the groups that were set aside, and exactly what was and wasn't checked.

| Ring graph and map | A group trip, ruled out |
|---|---|
| ![Ring graph and map](docs/screenshots/report.png) | ![A ruled-out group trip](docs/screenshots/trip-ruled-out.png) |

> Screenshots come from the synthetic demo fixtures. *(TODO before submission: replace them with a real showcase recorded in presentation mode, and add the report GIF.)*

A **Chrome extension** puts a badge on Google Maps place pages (level and rating without rings, or "Check reviews") and opens a side panel that runs an analysis on one explicit click, after showing its cost.

Everything that decides (labels, groups, levels, ratings) is deterministic and explained in [docs/methodology.md](docs/methodology.md). An optional AI model (DeepSeek) only writes a plain-language summary from numbered facts, under the evidence. A validator rejects any draft with a number, place name or loaded word it wasn't given.

## Why this needs SerpApi

ReviewRing can't exist without SerpApi. Google's official Places API returns **at most 5 reviews per place** and **no reviewer histories**. The reviewer history is the whole method.

| SerpApi engine | What ReviewRing uses it for |
|---|---|
| **Google Maps Contributor Reviews API** (`google_maps_contributor_reviews`) | A reviewer's public review history (up to 200 reviews, one search): what else they reviewed, where and when. It tells apart real customers (ordinary local lives) from linked groups and dormant accounts woken up for one review. |
| **Google Maps Reviews API** (`google_maps_reviews`) | The newest reviews, with exact dates and each reviewer's review count (bursts, single-use accounts, near-duplicate and chatbot text), and, sorted by highest rating, the old reviews that carry a listing's rating. |
| **Google Maps API** (`google_maps`) | Resolving a CID, a place_id-only link or a name search; the business's coordinates when no history contains them. |
| **Account API** (free) | The remaining monthly and hourly budget, shown before every analysis. |

When we checked (2026-09-26), none of the ~177 public BuiltWithSerpApi projects used the Contributor Reviews API.

## Quick start

Requires Python 3.12+ and Node 20+. [uv](https://docs.astral.sh/uv/) is recommended; a plain pip route is below.

### Demo mode (no keys, no network)

```bash
git clone https://github.com/kruxarth/serpapi-hackathon.git reviewring && cd reviewring
(cd web && npm install && npm run build)
cd backend && uv sync && uv run reviewring serve
# open http://127.0.0.1:8765
```

Without a SerpApi key the app starts in **demo mode**: prepared, pseudonymized analyses from `fixtures/`, re-run through the same engine and served by the same API.

<details><summary>Without uv (pip)</summary>

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
reviewring serve
```
</details>

### Live mode (your own SerpApi key)

```bash
cp .env.example .env        # add SERPAPI_API_KEY (and optionally DEEPSEEK_API_KEY)
cd backend && uv run reviewring serve
```

Paste a Google Maps link. You'll see the estimated cost (about 15 searches for a clean business, about 30 for a suspicious one) and your remaining budget before anything runs. Everything fetched is cached, so re-opening or re-analysing a place is free.

The same pipeline runs from the command line: `uv run reviewring --help` (`budget`, `dry-run`, `collect`, `resume`, `analyze`, `export`, `evaluate`, `purge-data`).

### Chrome extension

```bash
cd extension && npm install && npm run build
```

Then open `chrome://extensions`, enable Developer mode, click **Load unpacked** and pick `extension/dist`. Keep the backend running. The extension only ever talks to your local backend.

## Evaluation

`uv run reviewring evaluate` plants synthetic rings into clean businesses, replays the budgeted collection (priority score, round 1, early stop, round 2), and runs the engine on exactly what would have been fetched. It uses zero searches, fixed seeds and no AI. Results: [docs/evaluation/results.md](docs/evaluation/results.md).

![Credits vs recall](docs/evaluation/credits_vs_recall.png)

- Recall is reported **split by where each missed account was lost**: not chosen by the priority score, chosen but not grouped, or grouped but failing the ring rules.
- **Negative scenarios** must not be flagged: a wedding party, a family trip, a tour through two nearby states, a local circle of friends.
- A **harder-rings** table (aged accounts with photos and unique texts) shows where the method loses.
- **Honesty:** the planted rings follow our own model of a ring, so recall on them is optimistic. The false-positive estimate uses a small sample and comes with its 95% interval.

## Search efficiency

- **~15 searches** for a clean business, thanks to the early stop; **~30** for a suspicious one; a hard cap of 32.
- Every raw response is cached before it's parsed; a forced refresh adds a new version instead of overwriting.
- A budget guard enforces the monthly, hourly and per-analysis caps (the stricter of the local ledger and SerpApi's Account API) and pauses at the hourly limit. Resuming never requests anything twice.
- `dry-run` lists exactly which requests an analysis would make, from the cache alone.

## Responsible use, limitations and privacy

- **A pattern, not proof.** ReviewRing says "suspicious", "coordinated" or "ring-like pattern", never "fake" or "fraud", and it never declares a business or a person dishonest. Every claim links to visible evidence.
- **It doesn't flag everything.** Friends, families and group trips are set aside and shown as such, and "not checked" reviewers are neutral.
- **A business can be targeted without its knowledge.** Review-task scams hand recruits real businesses to review, so a ring-like group says nothing about whether the business asked for it.
- **Known limits:** rings within a single city aren't detected; colleagues who stay at the same hotels in several cities can look ring-like; regional travel-only rings show at most as "possible ring (trip-like)"; only the newest 88 reviews and 25 reviewers are examined; private profiles can't be checked; Google may already have removed some reviews.
- **The AI only writes summaries.** It sees pseudonymized facts, never names, profile links or ids, and it never sets a label, group, level or rating.
- **Privacy.** The local cache in `data/` holds personal data and is never committed (`uv run reviewring purge-data --yes` deletes it). Committed fixtures are pseudonymized (salted ids, "Business A/B", areas only, coordinates rounded to ~11 km, an approximate review count, every date shifted by a hidden per-business offset, review text dropped unless it's a truncated template shared by 3+ accounts) and pass a leak check. **Presentation mode** pseudonymizes the live app for recordings. Keys stay in `.env` and the backend and are redacted from every log. The backend binds to 127.0.0.1 and rejects cross-site requests.

## Project layout

| Path | Contents |
|---|---|
| `backend/` | Python package: SerpApi gateway, parsers, engine, API, exporter, evaluation, tests |
| `web/` | React + Vite + TypeScript app |
| `extension/` | Chrome extension (Manifest V3) |
| `fixtures/` | Pseudonymized analyses for demo mode |
| `config/reviewring.toml` | Every tunable threshold in one file |
| `docs/` | Methodology, evaluation, decisions, QA checklists |

Contributing: `pre-commit install` runs gitleaks and the fixture leak check on every commit. Tests (`uv run pytest` in `backend/`) never touch the network; any attempt fails the run.

## Hackathon details

- **Track:** Knowledge & Public Interest
- **AI tools used:** Claude Code (implementation, with a human-written spec and review); DeepSeek inside the product, optionally, for the plain-language summary only.
- **License:** MIT

# ReviewRing: system overview for reviewers

This document describes exactly how ReviewRing works as built (algorithm version 0.1.0, revised 2026-10-04 after one external review; see section 12): data flow, every algorithm and threshold, where each piece lives in the code, and the weak points we already know about. It's written so that someone who hasn't seen the code (a person or another LLM) can review the design critically. The final section lists the questions we most want challenged.

Context: an entry for the SerpApi India Hackathon 2026, judged on idea strength, originality, technical complexity, usefulness and meaningful SerpApi usage. Hard constraint: one free SerpApi account with **250 searches for the whole hackathon** (the plan renews after the deadline) and 50 searches per hour.

---

## 1. What it does, in one paragraph

Given a Google Maps business, ReviewRing fetches its newest reviews, picks the reviewers most worth a closer look, and fetches each one's **full public review history**. It then links two reviewers when they both reviewed the same *unrelated, distant* places. It looks for tight groups in that graph and rules out groups that look like ordinary group trips. A group is called a "ring" only when it spans several distant cities. The output is a suspicion level (Low / Elevated / High / Not enough history), the rating with ring reviews removed, and the evidence behind every claim. Everything that decides is deterministic. An optional LLM only writes a plain-language summary from pre-computed facts.

**Core hypothesis:** paid reviewers (review farms, and India's "rate hotels on Google Maps and earn" task scams) work in batches. The same accounts review the same set of unrelated client businesses across cities, and that pattern is invisible from one business's reviews alone.

---

## 2. Architecture

```
Google Maps link ──► resolver ──► collector ──► SerpApi gateway ──► SerpApi
                                     │              │ (cache, ledger, budget guard, key redaction)
                                     ▼              ▼
                               AnalysisInput ◄── SQLite cache (raw responses, versioned)
                                     │
                                     ▼
                          engine.analyze()  (pure, deterministic)
                                     │
                                     ▼
                     report JSON ──► FastAPI (127.0.0.1) ──► React web app
                                     │                    └► Chrome extension (MV3)
                                     └► optional LLM summary (DeepSeek, validated)
```

| Component | Path | Notes |
|---|---|---|
| SerpApi gateway | `backend/src/reviewring/serp/` | The only code path to SerpApi. |
| Input resolver | `resolve.py` | Turns Maps URLs, short links, CIDs, place_ids and name searches into a place. |
| Parsers | `parse.py`, `normalize/` | Raw JSON → model objects; dates, areas, text. |
| Collector | `collect.py` | The budgeted fetching strategy (rounds, early stop, pause/resume). |
| Engine | `engine/` | `features`, `target_signals`, `priority`, `graph`, `groups`, `accounts`, `analyze`. |
| Report and storage | `report.py`, `store.py`, `db.py` | The report JSON is stored per analysis. |
| API | `api/app.py`, `api/jobs.py` | One live analysis at a time; server-sent events for progress. |
| Privacy | `privacy.py`, `exporter.py`, `leakcheck.py` | Pseudonymization, fixtures, leak check. |
| LLM | `llm.py`, `prompts/` | DeepSeek (`deepseek-flash`), OpenAI-compatible API. |
| Evaluation | `evaluate.py`, `synth.py`, `fake_serp.py` | Planted rings, negative scenarios; zero searches. |
| Web app | `web/` | React + Vite + TS; Cytoscape graph, Leaflet map, Recharts timeline. |
| Extension | `extension/` | Badge on Maps place pages plus a side panel; talks only to the local backend. |
| Tunables | `config/reviewring.toml` | Every threshold below lives here. |

**Key design decision:** the engine is a pure function `analyze(AnalysisInput) → report`. Live collection, offline mode (cache only), demo mode (pseudonymized fixtures) and the evaluation harness all feed the same function.

---

## 3. Data sources (SerpApi engines)

| Engine | Used for | Cost |
|---|---|---|
| `google_maps_reviews` (`sort_by=newestFirst`, `hl=en`) | The business's newest reviews: exact `iso_date`, rating, text, reviewer `contributor_id`, reviewer review/photo counts. Page 1 = 8 reviews, later pages `num=20`, chained by `next_page_token`. | 1 per page |
| `google_maps_contributor_reviews` (`num=200`) | One reviewer's public history: each reviewed place's title, address, GPS, type and `data_id`, plus the rating, a **relative** date ("3 weeks ago") and the text. | 1 per reviewer |
| `google_maps` (`data_cid` / `place_id` / `q`) | Resolving non-`data_id` links and name searches; the business's coordinates if no history contains them. | 1 |
| Account API | Remaining monthly and hourly budget. | free |

Why SerpApi is essential: Google's official Places API returns at most 5 reviews per place and no reviewer histories.

---

## 4. Collection: the budgeted strategy (`collect.py`)

Default parameters: N = 100 newest reviews (6 pages), K1 = 8, B = 2 baseline, K2 = 15, hard cap 36 searches per analysis.

1. **Resolve** the place. A URL with a `data_id` costs 0 searches (parsed from the URL, along with the place's own coordinates from the `!8m2!3d…!4d…` token, never the viewport `@lat,lng`). Short links are followed with plain HTTP, not SerpApi. CID, place_id-only and name inputs cost 1 search.
2. **Fetch the newest 100 reviews** as one atomic step: 6 pages (108 reviews, the newest 100 kept). Before page 1, the budget guard checks that the month and the hour can cover all missing pages, because page tokens chain and a pause mid-way would force a restart.
3. **Score reviewers** (section 6.3) and pick round 1: the top K1 = 8 plus B = 2 random baseline reviewers from the lower-scoring half (seeded RNG keyed by the place).
4. **Expand round 1:** fetch 10 histories (3 in parallel).
5. **Early stop:** if no pair of round-1 reviewers forms an edge (section 6.5), stop and report "no ring-like pattern among the highest-priority reviewers". Cost so far is about 16 searches.
6. **Round 2:** otherwise take the next K2 = 15 by score, with a +2 bonus for reviewers whose review of the business is within ±3 days of a round-1 pick's, or a near-duplicate of one. Total is about 31 searches.
7. **Business coordinates:** taken for free from any fetched history that contains the business itself; otherwise 1 `google_maps` lookup by `data_cid`.

Pause, resume and cancel: every response is cached, so resuming re-runs the whole flow and cached requests cost nothing. Pauses happen only between reviewer histories.

---

## 5. Budget guard and storage (`serp/gateway.py`)

- **Persist before parse:** each raw response is written to `raw_responses` (keyed by a SHA-256 of the canonical, sorted parameters, excluding the key) before any parsing. A forced refresh adds a new version.
- **Request keys are frozen and pinned by tests,** so a cheap probe's responses are reused by the later full collection.
- **Ledger:** one row per request that reached SerpApi. Only `ok` and `empty` count as billed: SerpApi bills empty results but not errors.
- **Caps:** monthly, rolling-60-minute and per-analysis, from the ledger and the Account API, whichever is stricter. In-flight requests are reserved.
- **Errors:** 401 stops everything with no retry. 429 or the hourly cap pauses, with a computed resume time. 5xx and timeouts retry once after 30 s, then pause. A 400 is reported and not retried.
- **Secrets:** the `serpapi` client puts the key in the URL, and the wrapped `requests` exceptions quote that URL. A log-record factory therefore redacts the key and any `api_key=` value from every log line and traceback, and user-facing errors are built from status codes, never raw exception text.
- **Dry run** lists exactly which requests an analysis would make, from the cache alone.

---

## 6. The engine (`engine/`)

### 6.1 Normalization (`normalize/`)

- **Relative dates → absolute IST ranges**, computed from each response's own fetch time:

  | String | Days before the fetch |
  |---|---|
  | minutes or hours ago | 0–1 |
  | a day ago | 1–2 |
  | N days ago | N to N+1 |
  | a week ago | 7–14 |
  | N weeks ago | 7N to 7N+7 |
  | a month ago | 30–60 |
  | N months ago | 30N to 30N+30 |
  | a year ago | 365–730 |
  | N years ago | 365N to 365N+365 |

  A photo date inside the range moves its start up, because a review can't predate its photos. Precision = the range's width in days.
- **Areas:** for Indian addresses, the city is the component before the state (28 states and 8 UTs in config), with metro aliases merged (Gurugram, Noida and New Delhi → Delhi NCR; Thane → Mumbai; and so on). For non-Indian addresses the area is "City, Country". Unparseable addresses are clustered greedily within 50 km, in `place_key` order. Areas are only for counting and wording; "far" always uses haversine distance.
- **Text:** use `extracted_snippet.original`, never Google's translation. Normalize with NFKC, case-folding, and keep only letters, combining marks and digits (so Devanagari vowel signs survive). Similarity is the Jaccard index of character 3-gram sets; two texts are near-duplicates at ≥ 0.65 when both are ≥ 30 characters. "Short" means ≤ 40 normalized characters.
- **Clusters are anchored on the business's reviews:** only (business review, any text) pairs are compared, with different owners, then connected components. A second, business-reviews-only clustering is used by the priority score, so the expansion order never depends on histories fetched later.

### 6.2 Business-level signals T1–T5 (`target_signals.py`)

- **T1 bursts:** skipped if fewer than 10 dated reviews or a span under 2 days.
  - Baseline λ = reviews ÷ days × 3, per 3-day window.
  - A 3-day window (sliding, one per day) is flagged when it has ≥ 5 reviews, Poisson P(X ≥ n | λ) < 0.001, and ≥ 90% of its reviews are 5★ (positive) or ≥ 90% are 1★ (negative).
  - λ is recomputed without flagged windows for up to 3 rounds, so a dominant burst can't inflate its own baseline. Overlapping windows of the same direction are merged.
  - Bursts are framed neutrally ("consistent with a review drive or campaign") and never raise the level on their own.
- **T2:** rating histogram. **T3:** the share of 5★ reviews from accounts with ≤ 5 reviews, compared with the same share among ≤ 3★ reviews.
- **T4:** near-duplicate clusters among the business's reviews, minus stock phrases (6.6).
- **T5 young business:** fewer than 50 total reviews, or a sample spanning under 30 days with fewer than 200 total reviews.

### 6.3 Priority score (`priority.py`)

Each review with a `contributor_id` gets: +3 inside a burst; +2 if its rating matches the burst's direction (outside bursts, if it's 5★); +2 for a 5★ review outside a burst with ≥ 2 other 5★ reviews within ±24 h (small batches); +2 if the reviewer has ≤ 5 reviews; +1 for 0 photos; +1 for short text; +2 for being in a duplicate cluster. Local Guide status scores 0 on purpose: farms use aged accounts. Unknown values score 0. Each contributor keeps its best review; ties go to the newest.

### 6.4 Surprise weight of a shared place (`graph.py`)

*s(p)* = distance factor × type factor

- distance: < 5 km → 0.2; 5–50 km → 0.5; > 50 km → 1.0; unknown → 0.5 (and never "far"). The distance is to the business **or to either reviewer's home area, whichever is nearer**. A reviewer's home is the most common area among places no other checked reviewer reviewed; it needs ≥ 3 such places, and the top area must hold ≥ 2 of them and ≥ 40% (`engine/homes.py`).
- type factor 0.1 for "popular" types, else 1.0. A type is popular when its **last word** is on a list (attraction, airport, station, mall, park, temple, mosque, church, museum, fort, palace, beach, zoo, university, …), unless the whole type is on an exclusion list (police station, fire station). So "Water park" is popular and "Parking lot" isn't.

Adamic–Adar was rejected deliberately: it down-weights places shared by many sampled reviewers, and in our sample the ring's client places are exactly those.

### 6.5 Pair weight and edges

*W(u, v)* = Σ over shared places of *s(p)* × (1 + *c*), where *c* = 1.0 / 0.6 / 0.2 when both reviews of *p* have precision ≤ 2 / 14 / 60 days and their ranges overlap, else 0.

**Edge:** *W* ≥ 2.0 **and** at least 2 shared non-popular places. Two far, non-popular shared places give exactly 2.0, so detection never needs timing.

### 6.6 Stock phrases

A near-duplicate cluster used by ≥ 10 distinct accounts is a stock phrase when fewer than 20% of its **checked** users have an edge to another checked user of it. With fewer than 3 checked users it's undetermined and kept as evidence. It's excluded from T4 and A6. This is computed per analysis, after the graph exists.

### 6.7 Groups (`groups.py`)

1. Connected components of the edge graph. A component with ≥ 8 members and density < 0.5 is split with Louvain (fixed seed).
2. **Pruning:** repeatedly remove the single weakest member with fewer than max(2, ⌈30% × (size − 1)⌉) edges inside the group. Pruned members keep their own badges.
3. Metrics per group:
   - **core places:** non-popular places reviewed by ≥ max(3, ⌈30% × size⌉) members
   - **far areas:** distinct areas of core places > 50 km from the business, excluding its own area
   - **span:** the largest distance between core places
   - **type diversity:** distinct type groups among core places (Lodging, Food & drink, Tourist & religious, Event venue, Transport, Health, Education, Home & moving services, Retail, Beauty & wellness, Auto, Other)
   - **episodes:** core-place review dates with precision ≤ 14 days, clustered with a 21-day gap; "unknown" when fewer than half are that precise
   - **concentration:** the median, over members, of the share of their visible history (excluding the business) made up of places another member also reviewed
   - **core-place 5★ share**
   - **co-timing ratio:** the share of core-place reviews with *c* > 0 against another member's review of the same place; unknown under the episodes rule
4. **Social circle:** ≥ 50% of members share a home area **and** ≥ 50% of core places are within 50 km of it. Shown neutrally, never counted.
5. **Trip test:**
   - **Trip-like shape** = span ≤ 600 km (or no coordinates) **and** ≥ 75% of core places are in travel type groups (or all but one, with ≥ 3 core places) **and** episodes aren't known to be ≥ 2.
   - **Trip indicators:** episodes known to be exactly 1; concentration < 0.3; core 5★ share < 0.9.
   - **Positive evidence:** ≥ 50% of members share a home area, or ≥ 50% have a core-place hotel review whose `details` say they travelled as family, friends or a couple.
   - A trip-like shape with ≥ 2 indicators **and** positive evidence is **ruled out as a trip**: shown neutrally, never counted. It's reported only with ≥ 3 members and ≥ 2 core places.
   - Any other trip-like shape is **unresolved**: at most a possible ring-like group.
6. **Verdicts:**
   - **ring:** ≥ 4 members, density ≥ 0.5, ≥ 2 core places, ≥ 2 far areas, no trip-like shape.
   - **possible ring:** the same with 3 members.
   - **possible ring (trip-like):** an unresolved trip-like group with ≥ 3 members, density ≥ 0.5, ≥ 2 core places and ≥ 2 far areas.
   - otherwise **none**.
7. **Evidence strength** (named `confidence` in code; rings and possible rings only; not a probability):

   | Part | Value | Weight |
   |---|---|---|
   | Density | density | 0.20 |
   | Core places | min(core places ÷ 6, 1) | 0.15 |
   | Dispersion | min(far areas ÷ 4, 1) | 0.15 |
   | Type diversity | min(type groups ÷ 4, 1) | 0.10 |
   | Concentration | min(concentration ÷ 0.3, 1) | 0.15 |
   | Timing | co-timing ratio | 0.15 |
   | Member signals | share of members with ≥ 2 non-context signals | 0.10 |

   When timing is unknown, its part is dropped and the rest is renormalized (÷ 0.85).

### 6.8 Account signals (`accounts.py`)

For each expanded reviewer, using the visible history only:

| Signal | Rule |
|---|---|
| A1 thin profile | ≤ 5 reviews and 0 photos, or Local Guide level ≤ 2 when present |
| A2 rating monotony | ≥ 10 visible reviews, ≥ 95% of them 5★ |
| A3 several cities in one week (context) | Within 7 days (reviews with precision ≤ 7), ≥ 3 areas spanning ≥ 300 km |
| A4 same-day distant reviews (context; never called "impossible") | ≥ 2 occasions of overlapping day-precise reviews ≥ 500 km apart |
| A5 short texts | ≥ 60% of their texts are short |
| A6 copy-paste | Their review of the business is in a non-stock near-duplicate cluster with another account |
| A7 burst participant | Their review of the business falls inside a burst |
| A8 reworded template (optional LLM signal, context only, off by default) | Grouped by the paraphrase job with another reviewer |

### 6.9 Labels, rating and level (`analyze.py`)

- **Labels** (precedence top to bottom):
  - **ring:** member of a ring or a 3-member possible ring
  - **possible ring (trip-like)**
  - **suspicious:** expanded, not in a ring, has A6 plus ≥ 2 other signals; rare by design, since copied text is required
  - **trip or social group:** member of a ruled-out trip or a social circle; neutral
  - **no flags**
  - **not checked:** not expanded, or the fetch failed; neutral, hidden by default
- **Ratings:**
  - the mean of the examined reviews
  - the mean without ring-labelled reviews (the headline)
  - a stricter mean that also drops suspicious and possible-ring reviews
  - the **overall effect**, as a range: ((displayed ± 0.05) × total − Σ ring ratings) ÷ (total − ring reviews). When the range contains the displayed value, the report says "no visible change at the overall level".
- **Level** (first match wins):
  - **High:** a ring (not a possible ring) with confidence ≥ 0.7 whose reviews are ≥ 10% of those examined
  - **Elevated:** any ring or possible ring, or ≥ 15% of reviews labelled suspicious
  - **Not enough history:** every expanded history was empty or private, or a young business
  - **Low:** otherwise
- **Report:** place, sample, warnings, level and reasons, ratings, T1–T5, reviewers with badges, the graph (nodes, edges with shared places), groups with every metric and confidence part, per-review rows, **client lists** (each ring's core places plus places reviewed by ≥ 2 members), evidence sentences from fixed templates (each emitted only above a threshold), caveats, and analysis metadata including searches used.

---

### 6.10 Per-review warning signs and the sieve (`signs.py`; added 2026-10-07)

Each review gets every sign that applies, in config order: chatbot text, copied text, first-time accounts in a burst, linked reviewer group (strong, set aside at first), reads as AI-written (an LLM opinion with ≥ 2 quoted phrases that occur in the text; only reviews of ≥ 40 words), reviewing spree (A9) and first-time account (context, kept). The report carries `reviews[].signs`, `reviews[].ai` and a `sieve` summary; the web app and extension let the reader choose what to set aside and recompute the kept average. A first-time skew finding (T9) compares first-time shares among 5★ and other reviews. See `docs/methodology.md` section 6.

## 7. The optional LLM (`llm.py`)

- **Job 1, summary:**
  - The backend builds a numbered fact list (F1 = "the latest 100 reviews", F5 = "Jaipur, Kochi and Lucknow", …). Facts never name a reviewer; the business appears only as "this <type>".
  - The model must write 3–5 paragraphs that refer to facts only by `[Fn]`.
  - A deterministic validator rejects a draft containing an unknown id, a digit or number word outside a reference ("no one" is allowed), a known state, city or area name, or a banned word (fake, fraud, scam, paid, bought, bot, inauthentic, manipulate…, matched as whole words, so "unpaid" passes).
  - One retry with the complaints, then fixed templates. Ids are substituted by the backend.
  - The summary is shown below the evidence, collapsed by default.
- **Job 3, reads as AI-written:** reviews of ≥ 40 words, scrubbed, in batches of 12; a verdict of "ai_style" needs ≥ 2 quoted phrases found in the text, else "unclear". Shown as an opinion, kept by default, never counted.
- **Job 2, paraphrase signal A8:** off by default. Business-review texts are scrubbed (business words, phones, emails, URLs, handles) and sent with opaque indices; the reply groups reworded templates. A8 can never flag anyone on its own.
- **Safety:** an input check refuses payloads containing real names, contributor ids, review ids or URLs. Every call is cached by hash(model, prompt version, input) and stored before parsing. Offline and demo modes never call the API. Temperature is 0.

---

## 8. Privacy, safety and wording

- The local SQLite cache in gitignored `data/` holds personal data; `reviewring purge-data` deletes it.
- **Fixtures** (for demo mode and committed to git) are produced by the exporter:
  - ids are salted hashes (the salt stays in `data/`)
  - businesses become "<Type> A/B/…"; addresses become areas; coordinates are rounded to 1 decimal (~11 km); the review count is given to one significant figure; every date is shifted by a hidden per-business offset of 30–365 days (intervals unchanged)
  - review text is dropped unless it's in a near-duplicate cluster written by ≥ 3 accounts, and then it's scrubbed and cut to 60 characters
  - a leak check (URLs, emails, phones, PIN codes, every original id, name and title from the cache) blocks the export and runs as a pre-commit hook alongside gitleaks
- **Presentation mode** pseudonymizes reports on the server (same rounding, count bucketing and date shift), so real names never reach the browser during a recording.
- **API:** bound to 127.0.0.1. Every POST/PUT requires the header `X-ReviewRing: 1` plus a JSON content type, which forces a CORS preflight that only the web app's origins (and installed extensions) pass. A Host-header allowlist blocks DNS rebinding.
- **Wording:** "suspicious", "coordinated", "ring-like pattern"; never "fake" or "fraud" as a verdict. Caveats are always shown.
- **Extension:** never searches without an explicit click that shows the estimated cost and remaining budget. The content script never calls the backend; the service worker and side panel do.

---

## 9. Evaluation (`evaluate.py`; zero searches, fixed seeds)

- **Bases:** cached clean controls listed in `data/cases.toml` once they exist; until then, 3 synthetic clean businesses with 70 ordinary reviewers each.
- **Planting:** k synthetic accounts, each with a review of the business, m shared client places in ≥ 2 far areas, camouflage filler places, clustered dates, mostly 5★, and short template texts with edits.
- **Simulation:** collection is **replayed** (priority score, round 1, early stop, round 2) on base + planted data, and the engine runs on exactly what would have been fetched.
- **Grid:** k ∈ {3, 5, 8, 12, 20} × m ∈ {2, 4, 8} × camouflage ∈ {none, low, high} × timing ∈ {same day, same week, month, unknown}, plus a regional travel-only variant and a harder "aged accounts with photos and unique texts" variant.
- **Metrics:**
  - recall of planted accounts, split by where each loss happened: not chosen / not grouped / failed the ring rules
  - business-level detection
  - false-positive rate on unplanted accounts with a Wilson 95% interval
  - negative scenarios that must not be flagged (wedding party, family trip, two-state tour, local circle of friends)
  - a credits-vs-recall curve

**Current results (synthetic bases):**

| Measure | Result |
|---|---|
| Recall on harder rings (aged accounts, photos, unique texts, spread timing) | 83.0% (249/300); almost every loss is at the priority step |
| Recall on rings shaped like our own model | 99.1% (5135/5184) |
| Businesses with a planted ring rated High or Elevated | 98.9% |
| False positives on unplanted accounts | 0/30 (95% CI 0–11.4%) |
| Must-not-flag negative scenarios (sizes 3, 5, 8) | 6/6 pass, including hometown friends at a far resort and a package tour with an emporium |
| Known-limit scenarios | Friends from several cities at two weddings and cross-city family support circles are flagged (see section 12) |
| Trip-veto ablation | The old rule hid 61% of planted regional campaigns; the current rule hides none |

These numbers are **optimistic**: the planted rings follow our own model of a ring, and the bases are synthetic.

---

## 10. Known weaknesses and open questions

Not yet validated on real data. Zero real searches have been spent so far; the first real collection is the next step.

1. **Real response shapes are unconfirmed:**
   - what a private profile returns (we currently treat "profile present, 0 reviews" as private, "nothing" as empty)
   - whether history reviews carry `extracted_snippet`
   - how relative date strings line up with exact dates (calibration)
   - which `type` strings are common for Indian places (the popular-type and type-group lists are guesses)
2. **The priority score is the main bottleneck** in the harder-ring evaluation. Aged accounts with photos and unique text are rarely chosen, so a well-camouflaged farm can slip past within a budget of 25 histories.
3. **Single-city rings aren't detected by design** (they're indistinguishable from real local circles with this signal). Regional travel-only rings top out at "possible ring (trip-like)" and can't reach High.
4. **Colleagues at the same corporate hotels** in several cities can look ring-like. Concentration and diversity lower the confidence, but don't rule them out.
5. **Sampling:** only the newest 100 reviews and up to 25 reviewers are examined, and histories are capped at 200 reviews. A ring that posted months ago is outside the window.
6. **Thresholds are uncalibrated on real data:** edge W ≥ 2.0, core ≥ max(3, 30%), ring ≥ 4 members and ≥ 2 far areas, High at confidence ≥ 0.7 and ≥ 10% share.
7. **The false-positive estimate is thin** (30 accounts, synthetic), so its interval is wide.
8. **Text clustering is anchored on the business's reviews,** so duplicates that appear only between two histories aren't detected (A6 is defined on the business review, so this is intended, but it limits evidence).
9. **Stock-phrase "connected" status** is known only for expanded accounts; unexpanded users of a phrase count as unconnected, which biases towards calling it a stock phrase.
10. **Pruning removes one member at a time** (the spec said "repeatedly remove any"). That's more conservative and order-independent through sorting, but differs in edge cases.
11. **Label precedence** puts "suspicious" (copied text) above "group trip". That's debatable.
12. **Fixtures round coordinates** to 2 decimals (about 1 km), so distances near the 5 km and 50 km thresholds can shift. The stored fixture report is the re-run on the rounded data, so demo output stays consistent with itself.
13. **The overall-effect range** assumes Google's displayed rating is a simple mean of all ratings, which isn't guaranteed (this caveat is shown in the UI).

---

## 11. Questions we'd like a reviewer to challenge

1. Is "reviewed ≥ 2 of the same unrelated places > 50 km away" a strong enough edge to avoid false positives among real people? What realistic innocent populations would form dense multi-city groups (corporate travellers, pilgrimage circuits, wedding guests from several cities, delivery or field-sales staff, Local Guides doing "review challenges")?
2. Is the trip test (shape + 2 of 3 indicators) sound? Can a real ring easily satisfy it (a varied 4★/5★ mix, aged accounts with personal places), and can a real trip fail it?
3. Is the confidence formula sensible, or should it be replaced by something principled, such as a likelihood ratio against the baseline reviewers' overlap?
4. How should the priority score change to catch aged, camouflaged accounts without blowing the 25-history budget?
5. Is the evaluation methodology honest and informative enough for judges? What's missing?
6. Any privacy or safety gaps in publishing pseudonymized fixtures and a demo video of real businesses (with names hidden)?
7. Anything in the wording or presentation that could still read as an accusation against a business?

---

## 12. Changes after the first external review (2026-10-04)

| Review point | Change |
|---|---|
| Hometown friends at a far business look like a multi-city ring | Home areas; surprise uses the nearer of business and homes; neutral **social circle** verdict. New must-not-flag scenario passes. |
| The trip test vetoed on the *absence* of farm signs | Ruling out now needs **positive evidence** (shared home, or hotel details saying family/friends/couple). Ablation: the old rule hid 61% of planted regional campaigns by aged accounts; the new one hides none. |
| One emporium or pharmacy breaks a real tour's trip shape | All but one core place may be non-travel when there are ≥ 3. |
| Batches at busy places evade the burst test | +2 priority for a 5★ review with ≥ 2 other 5★ reviews within ±24 h. |
| Stock phrases judged on unexpanded accounts | Judged among checked users only; undetermined below 3. |
| Free date calibration | The report lists (relative string, true date) pairs from the business's own reviews found in histories. |
| The business itself is the re-identification risk | Date shift, count to 1 significant figure, coordinates to 1 decimal, in fixtures and presentation mode. |
| Wording implies payment | "Ring-like group", "excluding linked reviewers", "other places this group reviewed", "evidence strength (not a probability)", a standing caveat that businesses can be targeted without their knowledge, and a neutral Maps badge. |
| Evaluation leads with self-consistent numbers | The summary leads with harder-ring recall; negatives are a grid over sizes with social structures (hometown friends, package tour, family support circle, two-wedding friends, colleagues); the trip-veto ablation is reported. |

Checked against the SerpApi docs: contributor reviews carry text in `snippet` (the parser falls back to it), image dates are absolute, `hl=en` is in every frozen request key, and review `details` are now parsed for `travel_group`/`trip_type`.

**Deferred until real data:**
- a reverse co-client lookup: from one seed account, fetch a candidate co-client's newest reviews and intersect reviewer ids (finds aged accounts; costs searches)
- a curveball (degree-preserving shuffle) p-value per group
- route-order trip checks
- popular-type and type-group lists built from real type strings
- a cross-analysis popularity proxy

**Still open:**
- Friends from several cities who meet at two weddings, and cross-city family support circles, are flagged. The first is a false positive the design can't separate yet. The second is genuine coordination: we treat it as a wording issue, not a detection one.

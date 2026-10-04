# ReviewRing methodology

ReviewRing looks for **groups of reviewer accounts that reviewed the same unrelated businesses in distant cities**. A single paid review looks like any other review. Paid reviewers work in batches, though, and a batch shows up once you step from a business's reviews to each reviewer's full public review history.

Everything below is deterministic: the same cached data and the same `config/reviewring.toml` always give the same report. No AI model decides any label, group, level or rating.

## 1. Collection within a search budget

One analysis costs about 15 searches for a clean business and about 30 for a suspicious one (SerpApi free plan: 250 a month).

| Step | SerpApi engine | Searches |
|---|---|---|
| Newest 88 reviews of the business | `google_maps_reviews` (`sort_by=newestFirst`) | 5 (8 + 4 × 20) |
| Round 1: 8 highest-priority reviewers + 2 random baseline reviewers | `google_maps_contributor_reviews` (`num=200`) | 10 |
| Round 2, only if round 1 finds overlap: 15 more reviewers | `google_maps_contributor_reviews` | 15 |
| Business coordinates, only if no fetched history contains the business | `google_maps` (`data_cid`) | 0–1 |

**Priority score.** Each review gets points for being inside a review burst (+3), having the burst's rating (+2), being a 5★ review with at least 2 other 5★ reviews within 24 hours (+2; small batches at busy places), coming from an account with ≤ 5 reviews (+2) or no photos (+1), being short (+1), or being a near-duplicate of another review (+2). Local Guide status scores nothing: organised farms often use aged accounts, which is exactly what the graph method is built to catch. Unknown values score 0.

**Baseline.** Two reviewers are drawn at random (fixed seed) from the lower-scoring half. They show what normal overlap around this business looks like.

**Early stop.** If no pair of round-1 reviewers is connected (section 3), the analysis stops and reports "no ring-like pattern among the highest-priority reviewers". That saves about half the budget on clean businesses.

Every response is cached before it's parsed, so a parser bug never costs a re-fetch, and a paused or cancelled analysis resumes without requesting anything twice.

## 2. Normalization

- **Dates.** Reviewer histories give only relative dates ("3 weeks ago"). Each one becomes a range of IST calendar dates, computed from that response's own fetch time. A photo date inside the range moves its start up, because a review can't predate its photos. Timing therefore only ever *adds* weight; detection works without it.
- **Areas.** For Indian addresses, the city is the component before the state, with metro aliases merged (Gurugram, Noida and New Delhi all count as Delhi NCR). Areas are used for counting cities; the "far" test uses great-circle distance.
- **Text.** The original-language text is used, never Google's translation. Texts are normalized (NFKC, keeping Indic vowel signs) and compared by the Jaccard similarity of character 3-grams, which works for English, Hindi and Hinglish without a model. Two texts are near-duplicates at ≥ 0.65 similarity when both have ≥ 30 characters. A **stock phrase** (used by ≥ 10 accounts, fewer than 20% of the *checked* users connected to each other, with at least 3 checked users) is ignored. A ring pasting one template at many clients is connected, so it's never mistaken for one.

## 3. The co-review graph

For any place *p* two reviewers both reviewed (other than the business itself), its **surprise weight** is

*s(p)* = distance factor × type factor

- distance: < 5 km → 0.2, 5–50 km → 0.5, > 50 km → 1.0 (unknown → 0.5, never "far"). The distance is to the business **or to either reviewer's home area, whichever is nearer**. A reviewer's home is the most common area among their *personal* places (places no other checked reviewer reviewed). Friends from Pune sharing Pune cafés aren't surprising even when the business is in Goa; farm accounts' histories are mostly shared clients, so they usually have no home to discount.
- type: popular types (the type's last word is attraction, airport, station, mall, park, temple, museum, fort…) → 0.1, everything else → 1.0

The pair weight is *W(u, v)* = Σ *s(p)* × (1 + *c*), where *c* is 1.0, 0.6 or 0.2 when both reviews of *p* are dated to within 2, 14 or 60 days and their ranges overlap, and 0 otherwise. Two reviewers are **connected** when *W* ≥ 2.0 **and** they share at least 2 non-popular places. Two far, non-popular shared places are enough on their own, so detection doesn't depend on timing.

### Why not Adamic–Adar?

Link-prediction scores like Adamic–Adar weight each shared place by how *rare* it is among the reviewers in the sample. In our sample the places a ring shares are, by construction, the ones the most sampled reviewers share, so Adamic–Adar would suppress exactly the signal we want. The global popularity of a place isn't available without extra searches. Distance from the business and place type stand in for it: normal people's co-visits cluster near home and around landmarks, while paid rings span cities and unrelated trades.

## 4. Groups, trips and rings

Groups are the connected components of the graph. Components of ≥ 8 reviewers with density < 0.5 are split with Louvain (fixed seed). **Hangers-on are pruned**: members with fewer than max(2, 30% of the others) connections inside the group are removed one at a time, so an ordinary reviewer linked to a ring by a single edge doesn't inherit its label.

For each group ReviewRing computes: size, density, **core places** (non-popular places reviewed by ≥ max(3, 30%) of members), **far areas** (areas of core places > 50 km from the business, excluding its own area), span, type diversity, **episodes** (clusters of core-place review dates, with a gap > 21 days starting a new one), **concentration** (median share of each member's history made up of places other members also reviewed), the core-place 5★ share and the co-timing ratio.

### Friends and family

A group is a **social circle** when at least half its members share a home area and at least half its core places are within 50 km of that home. Real social groups share a life; farms share clients. Social circles are shown neutrally and never counted.

### The trip test

A family holiday also produces people who reviewed the same hotels and restaurants. A group has a **trip-like shape** when its core places are all travel businesses (lodging, food, sights, venues, transport) within 600 km, and it isn't known to have come back in several separate batches. Shape alone can't rule a group out, because a regional hotel ring has exactly this shape. So a trip-like group is judged on three **trip indicators**:

1. episodes are known to be exactly 1 (one visit window)
2. concentration < 0.3 (members' histories are mostly personal places)
3. core-place 5★ share < 0.9 (members rated the shared places differently)

A trip is **ruled out** only with 2 or more indicators **and positive evidence**: most members share a home area, or their hotel reviews say they travelled as family, friends or a couple. The absence of farm signs alone isn't enough; under that older rule, 61% of planted regional campaigns by aged accounts were hidden. Without positive evidence, a trip-like group can be at most a **possible ring-like group (trip-like pattern)**. One non-travel core place (a tour guide's emporium) doesn't break the trip shape when there are 3 or more. A group without a trip-like shape (e.g. a task-scam batch rating hotels across the country) is judged by the ring rules.

### Ring rules

- **Ring:** ≥ 4 members, density ≥ 0.5, ≥ 2 core places, ≥ 2 far areas, no trip-like shape.
- **Possible ring:** the same with 3 members, or an unresolved trip-like group of ≥ 3 that meets the structure rules. Possible rings are shown but weighted lower, and never make the level High.

### Evidence strength (shown as "confidence" in the code)

It's a weighted score, not a probability.

| Part | Value | Weight |
|---|---|---|
| Density | density | 0.20 |
| Core places | min(core places ÷ 6, 1) | 0.15 |
| Dispersion | min(far areas ÷ 4, 1) | 0.15 |
| Type diversity | min(type groups ÷ 4, 1) | 0.10 |
| Concentration | min(concentration ÷ 0.3, 1) | 0.15 |
| Timing | co-timing ratio | 0.15 |
| Member signals | share of members with ≥ 2 account signals | 0.10 |

When timing is unknown (most history dates are too coarse), the timing part is dropped and the rest is divided by 0.85. The report shows every part.

## 5. Account signals, labels and the level

Each checked reviewer gets badges: **A1** thin profile, **A2** rating monotony, **A3** several cities in one week (context), **A4** same-day distant reviews (context; people fly and batch-post trip reviews, so it's never called "impossible"), **A5** short texts, **A6** copy-paste text, **A7** burst participant, **A8** reworded template (optional, AI, context only).

Review labels: **ring**, **possible ring (trip-like)**, **suspicious** (needs A6 copied text plus 2 other signals, so it's rare by design: without copied text the graph is the only route to a flag), **group trip** (neutral), **not checked** (neutral, for reviewers whose history wasn't fetched) and **no flags**.

The **ring-adjusted rating** is the mean of the examined reviews without ring reviews, plus a stricter figure that also drops suspicious and possible-ring reviews. The overall effect is a range: (displayed rating ± 0.05) × total − ring ratings, divided by (total − ring reviews).

**Suspicion level:** **High** needs a ring (not a possible ring) with confidence ≥ 0.7 whose reviews are ≥ 10% of those examined. **Elevated** means any ring or possible ring, or ≥ 15% suspicious reviews. **Not enough history** covers a young business, or the case where every checked profile was empty or private. Otherwise the level is **Low**. Bursts, thin profiles and ruled-out trips never raise the level on their own.

## 6. The AI summary (optional)

With a DeepSeek key, a model writes a short plain-language summary **below** the evidence, collapsed by default. It only receives a numbered list of already-formatted, pseudonymized facts ("F3 = the latest 88 reviews") and may refer to them only by id. A deterministic validator rejects the draft if it references an unknown fact, or writes a digit, a number word, a place name, or any of fake / fraud / scam / paid / bot / manipulated (whole words). One retry, then fixed templates. The AI never sets a label, group, level or rating.

## 7. Known limits

- Rings that operate within a single city look like real local social circles; v1 doesn't flag them.
- Colleagues who stay at the same approved hotels in several cities can look ring-like. Concentration and diversity lower the confidence, but don't rule it out.
- Regional rings that only review travel businesses within about 600 km look like group trips; they show as possible rings (trip-like pattern) at most, unless their timing shows repeated batches.
- Only the newest 88 reviews and 25 reviewers are examined; histories are capped at 200 reviews; private profiles can't be checked; Google may already have removed some reviews.
- The evaluation plants rings that follow our own model of a ring, so its recall figures are optimistic (see `docs/evaluation/`).

## 8. Prior work and existing tools

ReviewRing builds on research into group spam detection:

- Mukherjee, Liu & Glance, "Spotting Fake Reviewer Groups in Consumer Reviews", WWW 2012: reviewer groups via frequent itemsets, with group-level indicators such as time windows and rating deviation.
- Beutel et al., "CopyCatch: Stopping Group Attacks by Spotting Lockstep Behavior in Social Networks", WWW 2013: lockstep behaviour in time as a group signal.
- Hooi et al., "FRAUDAR: Bounding Graph Fraud in the Face of Camouflage", KDD 2016: dense-subgraph detection that resists camouflage.

How ReviewRing differs from existing tools:

| Tool | What it does |
|---|---|
| The Transparency Company | Proprietary scores for US listings |
| ReviewProof | Browser extension with AI scoring of the reviews shown on the page |
| Fake Review Watch | Manual investigations of reviewer profiles, which ReviewRing automates |
| Fakespot, ReviewMeta | Amazon-focused; both have shut down |

ReviewRing is open source, shows the evidence behind every flag, rules out group trips instead of flagging them, publishes its evaluation, targets India's "rate hotels and earn" task-scam pattern, and gets its data through SerpApi instead of scraping.

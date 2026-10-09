# ReviewRing methodology

ReviewRing reads a business's **newest 100 reviews**, gives each one every **warning sign** that applies, and lets the reader set aside the signs they choose and read the rest (section 6). The signs come from the reviews themselves (chatbot text, copied text, bursts of first-time accounts), from the reviewers' full public histories (linked groups of accounts that reviewed the same unrelated businesses in distant cities, reviewing sprees) and, optionally, from an AI model's opinion of the text.

The linked-group method came first, but it isn't what real data mostly shows: the manipulation we found was cheap and one review at a time (bursts of accounts with no other reviews, pasted chatbot replies). A single paid review looks like any other review, and a single first-time account proves nothing, because most real customers review only once. The pattern shows in aggregate, and the reader gets to see it review by review.

Everything below is deterministic: the same cached data and the same `config/reviewring.toml` always give the same report. No AI model decides any label, group, level or rating.

## 1. Collection within a search budget

One analysis costs about 16 searches for a clean business and about 31 for one whose first reviewers are linked (SerpApi free plan: 250 a month). Searches are a developer concern: the app shows them only in its settings and in a "For developers" section of each report.

| Step | SerpApi engine | Searches |
|---|---|---|
| Newest 100 reviews of the business | `google_maps_reviews` (`sort_by=newestFirst`) | 6 (8 + 5 × 20 = 108, the newest 100 kept) |
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

Each checked reviewer gets badges: **A1** thin profile, **A2** rating monotony, **A3** several cities in one week (context), **A4** same-day distant reviews (context; people fly and batch-post trip reviews, so it's never called "impossible"), **A5** short texts, **A6** copy-paste text, **A7** burst participant, **A8** reworded template (optional, AI, context only), **A9** reviewing spree (context, section 6).

Review labels: **ring**, **possible ring (trip-like)**, **suspicious** (needs A6 copied text plus 2 other signals, so it's rare by design: without copied text the graph is the only route to a flag), **group trip** (neutral), **not checked** (neutral, for reviewers whose history wasn't fetched) and **no flags**.

The **ring-adjusted rating** is the mean of the examined reviews without ring reviews, plus a stricter figure that also drops suspicious and possible-ring reviews. The overall effect is a range: (displayed rating ± 0.05) × total − ring ratings, divided by (total − ring reviews).

**Suspicion level:** **High** needs a ring (not a possible ring) with confidence ≥ 0.7 whose reviews are ≥ 10% of those examined. **Elevated** means any ring or possible ring, or ≥ 15% suspicious reviews. **Not enough history** covers a young business, or the case where every checked profile was empty or private. Otherwise the level is **Low**. Bursts, thin profiles and ruled-out trips never raise the level on their own.

## 6. Warning signs and sorting the reviews

Each of the newest 100 reviews gets every sign that applies, in this order (strongest first):

| Sign | Rule | Strength | At first |
|---|---|---|---|
| Chatbot or template text | The text contains a fixed phrase no customer writes ("unable to generate", "[hotel name]", "as an AI") | strong | set aside |
| Copied text | In a near-duplicate cluster (section 2) with another account's text, excluding stock phrases. The report shows the review it matches, with the shared wording marked | strong | set aside |
| Written like a search ad | A "name or category, then place" phrase (within a few connecting words) that is the bare search term ("packers and movers in [area]", no distinctive name word), or two such phrases in one review; only when 3+ accounts and 8%+ of the reviews with text write any such phrase | strong | set aside |
| Part of a burst of same-star reviews | A 5★ (or 1★) review inside the busiest stretch of ≤ 72 hours of reviews with that rating (reviews > 12 hours from the rest trimmed off its ends), when that stretch holds ≥ 25% of the reviews examined (and ≥ 8) and arrives ≥ 10× faster than the listing's other reviews | strong | set aside |
| Linked reviewer group | The reviewer is in a ring or possible ring (sections 3 and 4) | strong | set aside |
| Reviewing spree (A9) | A checked reviewer whose busiest 31 days hold ≥ 8 non-popular places in ≥ 3 areas, ≥ 90% 5★ | context | kept |
| Names the business with its area | One such phrase that includes the business's own name ("Om Sai Packers and Movers, [area]"), at a listing where the search-ad test counts | context | kept |
| First-time account | The account shows ≤ 1 review | context | kept |

The report draws the reviews as dots flowing down a trunk; a review leaves at the **first** sign the reader has set aside and the rest reach **Kept**, with their average. Changing a sign moves exactly its reviews. The level (section 5) doesn't depend on the reader's choice.

**Why the writing matters most.** In real data (docs/research-2026-10-08.md) the linked-group model never appeared, and a single first-time account proved nothing. What separated listings was the text: search-ad phrasing repeated across accounts (two listings of nine, 0 elsewhere) and templates copied between accounts. The place words come from the end of the listing's address (its neighbourhood, city and state) plus metro aliases; the start of an address names buildings and landmarks that match ordinary words. Naming the business with its area once is how customers refer to it too, so that alone is context; only the bare search term or a repeat sets a review aside.

**Why there is no "not in the reviewer's own voice" sign.** It was tried on 2026-10-08: an AI model compared a review with the same account's other reviews. On real data nearly every flag was wrong. Most "other reviews" are one-line notes about a restaurant or a salon, and the model read a change of topic and length as a different writer; a stricter prompt that voted per review made it worse. Telling writers apart needs far more of a person's writing than a Google profile shows, so the check is switched off (`[voice] enabled = false`) and no longer opens extra reviewer histories for it.

**Why bursts are measured by the clock.** Google gives each review an exact timestamp, so a burst is told as it happened: "43 five-star reviews in 90 minutes on 12 Sep 2023 (35 of them within 39 minutes), while this listing usually gets one review every 18 days". Only reviews of the burst's rating count (a business buying praise buys 5★; someone attacking it posts 1★), and whose accounts they are doesn't decide anything: first-time accounts are reported in the sentence, not required, because the biggest burst we found at one mover came from established accounts. A slow stretch ("14 reviews in 7 days", two a day) is not a burst. Bursts that don't reach the bar still raise the priority of their reviewers.

**Why a single first-time account is only context.** On real listings, 15–20% of the 5★ reviews of an ordinary business come from accounts with no other reviews: people create an account to leave one review. Following Xie et al. (KDD 2012), who found that over 90% of reviewers write a single review and that bought singleton reviews show up as bursts correlated with rating, ReviewRing looks for the aggregate: the burst test above, and a **first-time skew** finding when 5★ reviews are at least twice as likely to come from first-time accounts as the other reviews (with ≥ 10 five-star and ≥ 5 other reviews, and ≥ 35% of the 5★ reviews from first-time accounts). Staff asking customers to review on the spot produces the same skew, so it is context, never a flag.

**Why there is no "reads as AI-written" sign.** It was built (an AI model's opinion on reviews of 40+ words, which had to quote two phrases from the text, kept by default) and switched off on 2026-10-08. AI-text detectors are unreliable on short texts and over-flag people writing in a second language (Liang et al., 2023, found 61% of non-native essays flagged), and on Indian listings the reviews it picked were mostly customers who had polished an honest review with AI. Using AI to write in a second language is not a warning sign, and labelling those reviews, even as a kept opinion, points readers at the wrong people. What remains is deterministic: fixed chatbot phrases ("I'm unable to generate a review", "[Hotel Name]") and text copied between accounts. The code stays behind `[ai_text] enabled`.

Behavioural signals beat text signals on real platforms (Mukherjee et al., ICWSM 2013: n-gram classifiers that scored ~90% on crowdsourced fakes scored 68% on Yelp's filtered reviews, while behavioural features held up), which is why the signs are behavioural or verbatim, with no judgement of style.

## 7. The AI summary (optional)

With a DeepSeek key, a model writes a short plain-language summary **below** the evidence, collapsed by default. It only receives a numbered list of already-formatted, pseudonymized facts ("F3 = the latest 100 reviews") and may refer to them only by id. A deterministic validator rejects the draft if it references an unknown fact, or writes a digit, a number word, a place name, or any of fake / fraud / scam / paid / bot / manipulated (whole words). One retry, then fixed templates. The AI never sets a label, group, level or rating.

## 8. Known limits

- Rings that operate within a single city look like real local social circles; v1 doesn't flag them.
- Colleagues who stay at the same approved hotels in several cities can look ring-like. Concentration and diversity lower the confidence, but don't rule it out.
- Regional rings that only review travel businesses within about 600 km look like group trips; they show as possible rings (trip-like pattern) at most, unless their timing shows repeated batches.
- Only the newest 100 reviews and 25 reviewers are examined; histories are capped at 200 reviews; private profiles can't be checked; Google may already have removed some reviews.
- A bought review from an established account, with its own words, posted outside a burst, carries no sign. Only reviewers whose histories were opened can show a spree or a linked group.
- A burst smaller than a quarter of the newest reviews isn't flagged, however fast (a listing that gets thousands of reviews needs a bigger sample than 100). A slow campaign spread over weeks isn't a burst at all.
- A review written entirely by a chatbot, without a leftover chatbot phrase, carries no sign.
- The evaluation plants rings that follow our own model of a ring, so its recall figures are optimistic (see `docs/evaluation/`).

## 9. Prior work and existing tools

ReviewRing builds on research into review spam detection:

- Xie, Wang, Lin & Yu, "Review Spam Detection via Temporal Pattern Discovery", KDD 2012: singleton reviews and bursts correlated with rating.
- Mukherjee, Venkataraman, Liu & Glance, "What Yelp Fake Review Filter Might Be Doing?", ICWSM 2013: behavioural features over linguistic ones on real data.
- Liang et al., "GPT detectors are biased against non-native English writers", 2023: why ReviewRing doesn't judge whether a review reads as AI-written.

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

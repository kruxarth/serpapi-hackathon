# Evaluation results

Algorithm version 0.1.0. Reproduce with `uv run reviewring evaluate` (fixed seeds, zero searches, no AI).

> Planted rings follow our own model of a ring, so recall on them is optimistic.

- **Bases:** synthetic-1 (Dental clinic, Pune), synthetic-2 (Restaurant, Bengaluru) (synthetic; no cached controls yet)
- **Recall of planted accounts:** 99.0% (491/496)
- **Lost: not chosen by the priority score:** 0.6%
- **Lost: chosen but not in any group:** 0.4%
- **Lost: grouped, but the group failed the ring rules:** 0.0%
- **Businesses with a planted ring rated High or Elevated:** 97.9%
- **False-positive rate on unplanted accounts:** 0/20 = 0.0% (95% Wilson interval 0.0%–16.1%; small sample)
- **Negative scenarios passed:** 4/4

![Credits vs recall](credits_vs_recall.png)

![Where planted accounts were caught or lost](recall_by_k.png)

## Recall by ring size (k)

| k | recall | not chosen | not grouped | failed rules | planted |
|---|---|---|---|---|---|
| 3 | 0.938 | 0.021 | 0.042 | 0.0 | 48 |
| 8 | 1.0 | 0.0 | 0.0 | 0.0 | 128 |
| 20 | 0.994 | 0.006 | 0.0 | 0.0 | 320 |

## Recall by shared places (m)

| m | recall | not chosen | not grouped | failed rules | planted |
|---|---|---|---|---|---|
| 2 | 0.984 | 0.008 | 0.008 | 0.0 | 248 |
| 4 | 0.996 | 0.004 | 0.0 | 0.0 | 248 |

## Recall by camouflage

| camouflage | recall | not chosen | not grouped | failed rules | planted |
|---|---|---|---|---|---|
| none | 1.0 | 0.0 | 0.0 | 0.0 | 248 |
| high | 0.98 | 0.012 | 0.008 | 0.0 | 248 |

## Recall by timing

| timing | recall | not chosen | not grouped | failed rules | planted |
|---|---|---|---|---|---|
| same week | 1.0 | 0.0 | 0.0 | 0.0 | 248 |
| unknown | 0.98 | 0.012 | 0.008 | 0.0 | 248 |

## Regional travel-only rings (within ~450 km)

| base | k | as_ring | as_possible_trip | planted | level |
|---|---|---|---|---|---|
| synthetic-1 (Dental clinic, Pune) | 5 | 0 | 5 | 5 | Elevated |
| synthetic-1 (Dental clinic, Pune) | 8 | 0 | 8 | 8 | Elevated |
| synthetic-2 (Restaurant, Bengaluru) | 5 | 0 | 5 | 5 | Elevated |
| synthetic-2 (Restaurant, Bengaluru) | 8 | 0 | 8 | 8 | Elevated |

## Harder rings: aged accounts, photos, unique texts, spread timing (information only)

| base | k | recall | not chosen | not grouped | failed rules | planted |
|---|---|---|---|---|---|---|
| synthetic-1 (Dental clinic, Pune) | 5 | 0.8 | 0.2 | 0.0 | 0.0 | 10 |
| synthetic-1 (Dental clinic, Pune) | 8 | 0.812 | 0.188 | 0.0 | 0.0 | 16 |
| synthetic-1 (Dental clinic, Pune) | 12 | 1.0 | 0.0 | 0.0 | 0.0 | 24 |
| synthetic-2 (Restaurant, Bengaluru) | 5 | 0.3 | 0.6 | 0.1 | 0.0 | 10 |
| synthetic-2 (Restaurant, Bengaluru) | 8 | 0.812 | 0.188 | 0.0 | 0.0 | 16 |
| synthetic-2 (Restaurant, Bengaluru) | 12 | 0.917 | 0.083 | 0.0 | 0.0 | 24 |

## Negative scenarios

| scenario | kind | flagged_share | result |
|---|---|---|---|
| Wedding party (one far city) | must not be flagged | 0.0 | PASS |
| Family trip, ordinary histories | must not be flagged | 0.0 | PASS |
| Tour through two nearby states | must not be flagged | 0.0 | PASS |
| Local circle of friends | must not be flagged | 0.0 | PASS |
| Group trip by thin accounts, all 5★ (expected: possible ring, trip-like) | information only | 1.0 | - |
| Colleagues at the same hotels in several cities (known limit) | information only | 0.0 | - |

## Clean bases without planted rings

| base | level | searches | early_stop |
|---|---|---|---|
| synthetic-1 (Dental clinic, Pune) | Low | 15 | True |
| synthetic-2 (Restaurant, Bengaluru) | Low | 15 | True |

## Credits vs recall (k=8, m=4, low camouflage, same week)

| histories | searches | recall |
|---|---|---|
| 4 | 9.0 | 0.5 |
| 6 | 11.0 | 0.75 |
| 8 | 13.0 | 0.958 |
| 10 | 15.0 | 0.958 |
| 13 | 18.0 | 1.0 |
| 16 | 21.0 | 1.0 |
| 20 | 25.0 | 1.0 |
| 25 | 30.0 | 1.0 |

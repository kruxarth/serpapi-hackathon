// Invented reviews for the home page: the product's own graph, working, before anyone pastes a link.
// Every review here is made up; the mix mirrors what real listings showed (a burst of first-time accounts,
// a copied template, polished AI-style texts and one pasted chatbot reply).

import type { ReviewRow, Sieve, SieveSign, SignKey } from './types'

const SIGNS: Record<SignKey, Omit<SieveSign, 'count' | 'mean' | 'set_aside_by_default'>> = {
  chatbot_text: { name: 'Chatbot or template text', short: 'Chatbot text', strength: 'strong', explain: 'Contains a phrase only a chatbot or an unfilled template produces.' },
  copied_text: { name: 'Copied text', short: 'Copied text', strength: 'strong', explain: 'Near-identical to a review that another account wrote.' },
  first_time_burst: { name: 'First-time accounts in a burst', short: 'Burst of first-time accounts', strength: 'strong', explain: 'Posted in a sudden burst of reviews from accounts that have reviewed nothing else.' },
  linked_group: { name: 'Linked reviewer group', short: 'Linked group', strength: 'strong', explain: 'The reviewer belongs to a group that reviewed the same unrelated businesses in distant cities.' },
  ai_style: { name: 'Reads as AI-written', short: 'Reads as AI-written', strength: 'opinion', explain: "An AI model's opinion, with the phrases it quotes. Not proof: real customers polish reviews with AI too." },
  review_spree: { name: 'Reviewing spree', short: 'Reviewing spree', strength: 'context', explain: 'The reviewer rated many businesses in several cities within a month, nearly all 5★.' },
  first_time_account: { name: 'First-time account', short: 'First-time account', strength: 'context', explain: 'No other reviews on the account. Many real customers do this.' },
}
const ORDER: SignKey[] = ['chatbot_text', 'copied_text', 'first_time_burst', 'linked_group', 'ai_style', 'review_spree', 'first_time_account']
const ASIDE: SignKey[] = ['chatbot_text', 'copied_text', 'first_time_burst', 'linked_group']
const ORDINARY = [5, 4, 5, 3, 4, 5, 2, 4, 5, 1, 4, 3, 5, 4, 4, 5, 3, 2, 5, 4]
const FIRST_TIME = [5, 5, 4, 3, 5, 1, 4, 5]

const mean = (v: number[]) => (v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 100) / 100 : null)

export function exampleSource(): { reviews: ReviewRow[]; sieve: Sieve; shown: number } {
  const rows: { rating: number; signs: SignKey[] }[] = []
  let o = 0
  const ordinary = (n: number) => { for (let i = 0; i < n; i++) rows.push({ rating: ORDINARY[o++ % ORDINARY.length], signs: [] }) }
  ordinary(9)
  rows.push({ rating: 5, signs: ['ai_style', 'first_time_account'] })
  ordinary(6)
  FIRST_TIME.slice(0, 4).forEach((r) => rows.push({ rating: r, signs: ['first_time_account'] }))
  rows.push({ rating: 5, signs: ['ai_style'] })
  ordinary(8)
  rows.push({ rating: 5, signs: ['chatbot_text', 'first_time_account'] })
  rows.push({ rating: 4, signs: ['ai_style'] }, { rating: 5, signs: ['copied_text'] })
  ordinary(10)
  for (let i = 0; i < 27; i++) {
    rows.push({ rating: 5, signs: i % 9 === 0 ? ['copied_text', 'first_time_burst', 'first_time_account'] : ['first_time_burst', 'first_time_account'] })
  }
  rows.push({ rating: 5, signs: ['copied_text'] }, { rating: 5, signs: ['ai_style', 'first_time_account'] })
  ordinary(12)
  FIRST_TIME.slice(4).forEach((r) => rows.push({ rating: r, signs: ['first_time_account'] }))
  rows.push({ rating: 5, signs: ['ai_style'] }, { rating: 5, signs: ['ai_style', 'first_time_account'] }, { rating: 5, signs: ['ai_style'] })
  ordinary(100 - rows.length)

  const reviews = rows.slice(0, 100).map((r, i) => ({
    review_id: `example-${i}`, contributor_id: null, rating: r.rating, date: null, day: null, label: 'no_flags', badges: [],
    text: null, text_length: null, script: null, cluster: null, stock_phrase: false, short: false, reviewer_reviews: null,
    local_guide: null, signs: r.signs, ai: null,
  })) as ReviewRow[]
  const signs = Object.fromEntries(ORDER.map((k) => {
    const having = reviews.filter((r) => r.signs!.includes(k)).map((r) => r.rating!)
    return [k, { ...SIGNS[k], count: having.length, mean: mean(having), set_aside_by_default: ASIDE.includes(k) }]
  })) as Record<SignKey, SieveSign>
  const kept = reviews.filter((r) => !r.signs!.some((s) => ASIDE.includes(s))).map((r) => r.rating!)
  const all = reviews.map((r) => r.rating!)
  const sieve: Sieve = {
    order: ORDER, set_aside_by_default: ASIDE, signs, examined: reviews.length,
    kept: { count: kept.length, mean: mean(kept) },
    no_signs: { count: reviews.filter((r) => !r.signs!.length).length, mean: null },
    all: { count: all.length, mean: mean(all) },
    ai: { min_words: 40, eligible: 0, judged: 0, too_short: 0, no_text: 0, ai_style: 0, human_style: 0, unclear: 0, model: null },
  }
  return { reviews, sieve, shown: 4.8 }
}
